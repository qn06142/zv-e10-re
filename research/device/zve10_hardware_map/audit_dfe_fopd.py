"""Verify selected FOPD register operations in a saved ZV-E10 firmware image."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from unicorn import UC_ARCH_ARM, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_MODE_THUMB, Uc
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP

IMAGE_BASE = 0x635C6000
IMAGE_SHA256 = "bc6cba98c1ce5ef9c7692b9701ed855c25958d285a646ef90dc3fdf398f5c4fa"
SCRATCH = 0x20000000
RETURN = SCRATCH + 0x100
MMIO = 0xF3020000
ROUTE = 0xF302078C
ROUTE_COMPANION = 0xF3020790
SHIFTS = (0, 4, 8, 12, 16)


def pack(value):
    return struct.pack("<I", value)


def expected_route(seed, mask, selector, clear_matches):
    result = seed
    for bit, shift in enumerate(SHIFTS):
        old = (seed >> shift) & 3
        if mask & (1 << bit):
            value = selector
        elif clear_matches and old == selector:
            value = 3
        else:
            continue
        result = (result & ~(3 << shift)) | (value << shift)
    return result


def audit(image):
    digest = hashlib.sha256(image).hexdigest()
    if digest != IMAGE_SHA256:
        raise ValueError(f"Unreviewed firmware SHA-256: {digest}")
    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    cpu.mem_map(IMAGE_BASE, (len(image) + 0xfff) & ~0xfff)
    cpu.mem_write(IMAGE_BASE, image)
    cpu.mem_map(SCRATCH, 0x2000)
    cpu.mem_map(MMIO, 0x10000)
    events = []

    def observe(_cpu, access, address, size, value, kind):
        events.append((kind, address, size, value if kind == "write" else None))

    for hook, kind in ((UC_HOOK_MEM_READ, "read"), (UC_HOOK_MEM_WRITE, "write")):
        cpu.hook_add(hook, observe, kind, begin=MMIO, end=MMIO + 0xffff)

    def run(entry, *args):
        events.clear()
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2), args):
            cpu.reg_write(reg, value)
        cpu.reg_write(UC_ARM_REG_SP, SCRATCH + 0x1ff0)
        cpu.reg_write(UC_ARM_REG_LR, RETURN | 1)
        cpu.emu_start(entry | 1, RETURN, count=600)
        assert cpu.reg_read(UC_ARM_REG_PC) == RETURN
        return list(events)

    trials = 0
    for seed in (0xABCDEF01, 0x5A000000, 0xFE3F3F3F, 0xA5FCDEE4):
        for mask in range(32):
            cpu.mem_write(SCRATCH, bytes([mask]))
            for selector in range(4):
                for clear in (0, 1):
                    cpu.mem_write(ROUTE, pack(seed))
                    assert run(0x63D20D80, SCRATCH, selector, clear) == [
                        ("read", ROUTE, 4, None),
                        ("write", ROUTE, 4, expected_route(seed, mask, selector, clear)),
                    ]
                    trials += 1
            cpu.mem_write(ROUTE, pack(seed))
            companion = sum(1 << shift for bit, shift in enumerate(SHIFTS) if mask & (1 << bit))
            actual = run(0x63D20E4E, SCRATCH, 0x80)
            assert actual == [
                ("read", ROUTE, 4, None),
                ("write", ROUTE, 4, expected_route(seed, mask, 3, 0)),
                ("write", ROUTE_COMPANION, 4, companion | 0x80),
                ("write", ROUTE_COMPANION, 4, 0),
            ], (seed, mask, actual)
            trials += 1

    seed = 0xABCDEF01
    for selector in (0, 2):
        cpu.mem_write(SCRATCH, bytes([0x15]))
        cpu.mem_write(ROUTE, pack(seed))
        assert run(0x63D1F296, SCRATCH, selector) == [
            ("read", ROUTE, 4, None),
            ("write", ROUTE, 4, expected_route(seed, 0x15, selector, 1)),
        ]
        trials += 1

    slot_writes = []
    for selector, entry in enumerate((0x63D1F26C, 0x63D1F27A, 0x63D1F288)):
        payload = 0x11223300 + selector
        address = 0xF3020518 + selector * 0x40
        assert run(entry, payload) == [("write", address, 4, payload)]
        slot_writes.append(f"{address:#010x}")
        trials += 1

    sideband = []
    for stream_flag in (0, 1):
        assert run(0x63D1F348, stream_flag) == [
            ("write", 0xF30207B8, 4, stream_flag),
            ("write", 0xF30207BC, 4, stream_flag),
        ]
        assert run(0x63D1F354, stream_flag) == [("write", 0xF30207B4, 4, stream_flag)]
        sideband.append(stream_flag)
        trials += 2

    table = struct.unpack_from("<9I", image, 0x645F2114 - IMAGE_BASE)
    assert table == (
        0x63D1F26D, 0x63D1F243, 0x63D1F219,
        0x63D1F27B, 0x63D1F251, 0x63D1F227,
        0x63D1F289, 0x63D1F25F, 0x63D1F235,
    )
    # Reference table records are unit base, channel base, then flag/nibble bytes.
    channels = []
    for index, label in enumerate(("R0", "W0", "W1", "W2", "W3", "W4")):
        channel_id = 0x11 + index
        base = MMIO + 0x200 + 0x80 * index
        assert struct.unpack_from("<3I", image, 0x63E89724 - IMAGE_BASE + channel_id * 12) == (
            MMIO, base, (index << 8) | int(index != 0),
        )
        channels.append({"id": hex(channel_id), "firmware_label": label, "base": hex(base)})

        cfg = SCRATCH + 0x200
        address_word, word20, word24 = 0x12345600, 0x11223344, 0x55667788
        for mode, busy, repeat in ((0, 0, 0), (3, 0, 0), (3, 1, 1), (3, 1, 0)):
            cpu.mem_write(cfg, bytes((2, 1, 1, repeat, 0xB, mode, 0, 0)) +
                          struct.pack("<3I", word20, word24, address_word))
            cpu.mem_write(base, pack(0x20 if repeat else 0))
            cpu.mem_write(base + 4, pack(busy << 31))
            expected = []
            if index:
                expected.append(("read", base + 4, 4, None))
                if busy:
                    expected.append(("read", base, 4, None))
            if not (index and busy and repeat):
                expected.append(("write", base + 0x0C, 4, address_word if index else 0))
            control = 0x1C | (0x20 if index and repeat else 0) | (0xB0800 if mode == 3 else 0)
            expected.extend([
                ("write", base + 0x24, 4, word24),
                ("write", base + 0x20, 4, 0xFF000000 if mode == 3 else word20),
                ("write", base, 4, control),
                ("read", base, 4, None),
            ])
            actual = run(0x639E1F98, channel_id, cfg)
            assert actual == expected, (label, mode, busy, repeat, actual, expected)
            assert cpu.mem_read(0x643E8A68, 4) == pack(control)
            trials += 1

        if index:
            # FOPD write channels consume a request with a buffer address in its +0x0c word.
            cpu.mem_write(cfg, bytes((1, 0, 0, 0)) + struct.pack("<3I", 0x55A8, 0, address_word))
            cpu.mem_write(base, pack(0))
            cpu.mem_write(base + 4, pack(1 << 31))
            cpu.mem_write(base + 0x1C, pack(0))
            assert run(0x63D1F1BC, channel_id, cfg) == [
                ("read", base + 0x1C, 4, None),
                ("read", base, 4, None),
                ("read", base + 4, 4, None),
                ("read", base, 4, None),
                ("write", base + 0x0C, 4, 0),
                ("write", base + 0x24, 4, 0x55A8),
                ("write", base + 0x20, 4, address_word),
                ("write", base, 4, 2),
                ("read", base, 4, None),
                ("read", base + 4, 4, None),
            ]
            assert cpu.reg_read(UC_ARM_REG_R0) == 0
            cpu.mem_write(cfg + 0xC, pack(address_word | 1))
            assert run(0x63D1F1BC, channel_id, cfg) == [("read", base + 0x1C, 4, None)]
            assert cpu.reg_read(UC_ARM_REG_R0) == 0xFFFFFFF8
            trials += 2

        dimensions = (17, 29, 31, 47)
        values = (1000, 2000, 3000, 4000)
        cpu.mem_write(cfg, struct.pack("<4H4I", *dimensions, *values))
        geometry_writes = [
            ("write", base + 0x28 + 4 * slot, 4, value)
            for slot, value in enumerate(v for pair in zip(values, dimensions) for v in pair)
        ]
        assert run(0x639E2140, channel_id, cfg) == geometry_writes + [("read", base + 0x44, 4, None)]
        trials += 1

        for entry, offset, value, updated in (
            (0x639E21E0, 0, 0xA0, 0xA1),
            (0x639E22EC, 4, 0x80000001, 0x80000000),
            (0x639E226C, 0, 0xA1, 0xA0),
            (0x639E2210, 4, 0x80000000, 0xC0000000),
        ):
            word = base + offset
            cpu.mem_write(word, pack(value))
            assert run(entry, channel_id) == [
                ("read", word, 4, None), ("write", word, 4, updated), ("read", word, 4, None),
            ]
            assert cpu.mem_read(0x643E8A68, 4) == pack(updated)
            trials += 1

        for bit in (0, 1):
            cpu.mem_write(base, pack(0x20 | bit))
            cpu.mem_write(base + 4, pack(0x3FFFFFFF | (bit << 31)))
            for entry, word in ((0x63793988 + 0x10 * index, base),
                                (0x637939E8 + 0x0C * index, base + 4)):
                assert run(entry) == [("read", word, 4, None)]
                assert cpu.reg_read(UC_ARM_REG_R0) == bit
                trials += 1

        cpu.mem_write(base + 0x10, pack(address_word + 0x120))
        assert run(0x639E231C, channel_id) == [("read", base + 0x10, 4, None)]
        assert cpu.reg_read(UC_ARM_REG_R0) == address_word + 0x120
        trials += 1

        status_word = 0xF3020000
        cpu.mem_write(status_word, pack(0x00654321))
        assert run(0x639E20DC, channel_id) == [("read", status_word, 4, None)]
        assert cpu.reg_read(UC_ARM_REG_R0) == index + 1
        assert run(0x639E2108, channel_id, 0x12) == [
            ("write", status_word, 4, 2 << (4 * index)), ("read", status_word, 4, None),
        ]
        trials += 2


    return {
        "image_sha256": digest,
        "image_base": hex(IMAGE_BASE),
        "camera_access_performed": False,
        "verified_instruction_runs": trials,
        "fopd_entries": ["0x63b61540", "0x63b618c8"],
        "route": {
            "address": hex(ROUTE),
            "width_bits": 32,
            "selector_shifts": SHIFTS,
            "selector_bits": 2,
            "clear_matching_value": 3,
            "companion_address": hex(ROUTE_COMPANION),
            "clear_mask_entry": "0x63d20e4e",
            "companion_sequence": ["incoming r1 OR one bit per enabled field", "0"],
        },
        "dispatch_table": {"address": "0x645f2114", "thumb_pointers": [hex(p) for p in table]},
        "first_dispatch_writes": slot_writes,
        "fopd_aif": {
            "reference_channel_table": "0x63e89724",
            "channels": channels,
            "configuration_entry": "0x639e1f98",
            "auxiliary_config_word_offset": "0x10",
            "auxiliary_channel_word_offset": "0x0c",
            "write_buffer_request_entry": "0x63d1f1bc",
            "write_buffer_input_offset": "0x0c",
            "write_buffer_normal_mmio_offset": "0x20",
            "current_address_read_entry": "0x639e231c",
            "current_address_mmio_offset": "0x10",
            "geometry_entry": "0x639e2140",
            "start_bit": 0,
            "secondary_word_cleared_bit": 0,
            "secondary_word_stop_bit": 30,
            "secondary_word_status_bit": 31,
            "unit_status_address": "0xf3020000",
            "unit_status_nibble_shift": "4 * (channel_id - 0x11)",
            "unit_status_read_entry": "0x639e20dc",
            "unit_status_write_entry": "0x639e2108",
        },
        "fopd_sideband_writes": {
            "addresses_in_order": ["0xf30207b8", "0xf30207bc", "0xf30207b4"],
            "observed_immediate_values_by_path": [[flag, flag, 0] for flag in sideband],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not __debug__:
        parser.error("Run without Python optimization to retain instruction assertions")
    report = audit(args.firmware.read_bytes())
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f'{report["verified_instruction_runs"]} original-instruction cases passed')


if __name__ == "__main__":
    main()
