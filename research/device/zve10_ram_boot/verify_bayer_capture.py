"""Verify the ZVOS still Bayer loop with a modeled ISP0 AIF writer."""
import argparse
import struct
import zlib
from pathlib import Path

from unicorn import UC_ARCH_ARM, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_MODE_ARM, Uc
from unicorn.arm_const import (
    UC_ARM_REG_CPSR,
    UC_ARM_REG_LR,
    UC_ARM_REG_R0,
    UC_ARM_REG_SP,
)

from build_rtos import HEADER, MAGIC, VERSION

HANDOFF_MAGIC = int.from_bytes(b"ZVRH", "little")
PROBE_OK = 0x4F4B5254
ARENA_BYTES = 0x10000
FRAME_BYTES = 614400
STRIDE_PIXELS = 6048
LIVE_HEIGHT = 4024
RAW_BASE = 0x35000000
RAW_BYTES = STRIDE_PIXELS * LIVE_HEIGHT * 2
ISP0 = 0xF3002380


def inject_test_raw(uc, buf_va, swapped):
    """Fill the modeled 14-bit RGGB frame with two distinguishable areas."""
    top_even = struct.pack("<HH", 0x3C00, 0x0000) * (STRIDE_PIXELS // 2)
    top_odd = struct.pack("<HH", 0x0000, 0x0000) * (STRIDE_PIXELS // 2)
    bot_even = struct.pack("<HH", 0x0000, 0x0000) * (STRIDE_PIXELS // 2)
    bot_odd = struct.pack("<HH", 0x0000, 0x3C00) * (STRIDE_PIXELS // 2)
    if swapped:
        top_even, bot_even = bot_even, top_even
        top_odd, bot_odd = bot_odd, top_odd
    half = LIVE_HEIGHT // 2
    uc.mem_write(buf_va, (top_even + top_odd) * (half // 2))
    uc.mem_write(buf_va + RAW_BYTES // 2, (bot_even + bot_odd) * (half // 2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--no-dma", action="store_true", help="exercise the no-progress timeout path")
    args = parser.parse_args()
    image = args.image.read_bytes()
    magic, version, header_bytes, code_bytes, entry, checksum, flags, reserved = HEADER.unpack_from(image)
    code = image[header_bytes:]
    assert (magic, version, header_bytes, flags, reserved) == (MAGIC, VERSION, 32, 1, 0)
    assert code_bytes == len(code) and zlib.crc32(code) == checksum

    cpu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    base, context, stack, arena, stop = 0x5F100000, 0x5F200000, 0x5F300000, 0x65000000, 0x5F400000
    frame_pa = 0x22C48000
    frame_va = frame_pa + 0x60000000

    for start, size in (
        (base, (len(code) + 0xFFF) & ~0xFFF),
        (context, 0x1000),
        (stack, 0x2000),
        (arena, ARENA_BYTES),
        (stop, 0x1000),
        (0x81000000, 0x200000),
        (0x81E00000, 0x200000),
        (0x85000000, 0x1000000),
        (0x86000000, 0x100000),
        (RAW_BASE + 0x60000000, 0x03000000),
        (0x64419000, 0x3000),
        (0x643EB000, 0x1000),
        (frame_va & ~0xFFF, (FRAME_BYTES + 0x2000) & ~0xFFF),
        (0xF2403000, 0x1000),
        (0xF2406000, 0x1000),
        (0xF2407000, 0x1000),
        (0xF2900000, 0x1000),
        (0xF290E000, 0x1000),
        (0xF2910000, 0x3000),
        (0xF292A000, 0x1000),
        (0xF2931000, 0x1000),
        (0xF2A00000, 0x1000),
        (0xF2A30000, 0x1000),
        (0xF3120000, 0x1000),
        (0xF3122000, 0x2000),
        (ISP0 & ~0xFFF, 0x1000),
        (0xF3440000, 0x7000),
        (0xF0000000, 0x1000),
        (0xF0010000, 0x1000),
        (0xF0030000, 0x1000),
        (0xF0105000, 0x1000),
        (0xF8000000, 0x3000),
        (0xFC000000, 0x400000),
    ):
        cpu.mem_map(start, size)

    cpu.mem_write(base, code)
    handoff = [
        HANDOFF_MAGIC, VERSION, 32, 7, arena, 0x05000000, ARENA_BYTES,
        0, 0x02000800, FRAME_BYTES, 0, 0,
    ]
    cpu.mem_write(context, HEADER.pack(*handoff[:8]) + struct.pack("<4I", *handoff[8:]))
    for ch in range(0x39, 0x41):
        cpu.mem_write(0x643EB19C + ch * 4, struct.pack("<I", 0x22B))
    desc = [frame_pa, 0x01E00280, 0, 0x01E00280, 0, 0, 0, 0, 0, 0, 1, 0x5F04001E, 0x63733989, 0]
    cpu.mem_write(0x6441B27C, struct.pack("<14I", *desc))

    cpu.mem_write(0xF3445000, struct.pack("<I", 0x00010114))
    cpu.mem_write(0xF3446000, struct.pack("<I", 0x00000000))
    cpu.mem_write(0xF3440144, struct.pack("<I", 0x02000233))
    cpu.mem_write(0xF3440404, struct.pack("<I", 0x00000000))
    cpu.mem_write(0xF344042C, struct.pack("<I", 0x000001E0))
    cpu.mem_write(0xF3441300, struct.pack("<I", 0x00000003))
    cpu.mem_write(0xF3441304, struct.pack("<I", 0x80000000))
    cpu.mem_write(0xF3441310, struct.pack("<I", 0x22C84E80))
    cpu.mem_write(0xF8002100, struct.pack("<I", 1))
    cpu.mem_write(0xF290E004, struct.pack("<I", 1))
    cpu.mem_write(0xF290E008, struct.pack("<I", 1))
    cpu.mem_write(0xF0105068, struct.pack("<I", 0x10000))
    cpu.mem_write(0xF01050A0, struct.pack("<I", 0x01000000))
    cpu.mem_write(0xF01050A4, struct.pack("<I", 1))
    cpu.mem_write(0xF0105148, struct.pack("<I", 0x20200010))
    cpu.mem_write(0xF0105090, struct.pack("<I", 0x00240000))

    state = {
        "tick": 1000,
        "l2_syncs": 0,
        "flips": 0,
        "power_writes": [],
        "seq_bursts": [],
        "seq_run_modes": [],
        "current_burst": [],
        "armed": 0,
        "triggered": 0,
        "dma_start_flip": None,
        "stopped": False,
        "timeout_snapshot": None,
        "lcd_frame_pairs": [],
        "returned_to_status": False,
    }
    adc0_base, adc1_base = 0xF2406000, 0xF2407000
    adc_started = {1: None}

    def key_value(ctrl, channel, flip):
        if ctrl == 1 and channel == 0:
            exit_at = 40 if args.no_dma else 20
            return 0x000 if flip in (exit_at, exit_at + 1) else 0x3FF  # DELETE
        if flip in (1, 2, 5, 6):
            return 0x1FA  # DOWN (0 -> 1 -> 2)
        if flip in (9, 10):
            return 0x000  # OK -> launch Live Bayer RAW
        return 0x3FF

    def on_read(uc, _access, address, _size, _val, _ud):
        if address == 0xF240310C:
            state["tick"] += 35000
            uc.mem_write(address, struct.pack("<I", state["tick"]))
        elif address == 0xF80027BC:
            uc.mem_write(address, struct.pack("<I", 0))
        elif address in (adc0_base + 0x10, adc1_base + 0x10):
            uc.mem_write(address, struct.pack("<H", 0))
        elif address in (adc1_base + 0x14, adc1_base + 0x20):
            channel = 0 if address == adc1_base + 0x14 else 3
            started_flip, started_tick, selected_channel = adc_started[1]
            assert started_flip == state["flips"] and state["tick"] - started_tick >= 50
            assert channel == selected_channel
            uc.mem_write(address, struct.pack("<H", key_value(1, channel, state["flips"])))
        elif address == 0xFC0F00AC and args.no_dma and state["triggered"]:
            control, = struct.unpack("<I", uc.mem_read(ISP0, 4))
            state["timeout_snapshot"] = control
        elif address == ISP0 + 4 and state["dma_start_flip"] is not None:
            elapsed = state["flips"] - state["dma_start_flip"]
            if elapsed < 2 or state["triggered"] == 4:
                # Keep the fourth transfer busy so DELETE exercises the stop path.
                status, position = 0x80000000, RAW_BASE + RAW_BYTES * min(elapsed + 1, 2) // 3
            else:
                status, position = 0, 0
                inject_test_raw(uc, RAW_BASE + 0x60000000, state["triggered"] % 2 == 0)
                state["dma_start_flip"] = None
            uc.mem_write(ISP0, struct.pack("<I", 2))
            uc.mem_write(ISP0 + 4, struct.pack("<I", status))
            uc.mem_write(ISP0 + 0x10, struct.pack("<I", position))
        elif address == ISP0 + 4 and state["stopped"]:
            uc.mem_write(address, struct.pack("<I", 0))
        elif address == 0xF3441300 and state["l2_syncs"] >= 2:
            uc.mem_write(address, struct.pack("<I", 2))
        elif address == 0xF3441304:
            cur = struct.unpack("<I", uc.mem_read(address, 4))[0]
            if cur & 0x40000000:
                uc.mem_write(address, struct.pack("<I", cur & ~0x80000000))

    def on_write(uc, _access, address, _size, value, _ud):
        if address == adc1_base + 4 and value == 1:
            selected, = struct.unpack("<H", uc.mem_read(adc1_base, 2))
            adc_started[1] = (state["flips"], state["tick"], selected.bit_length() - 1)
        elif address == 0xF8002730:
            state["l2_syncs"] += 1
            uc.mem_write(0xF8002730, struct.pack("<I", 0))
        elif 0xFC029000 <= address <= 0xFC02A0FF:
            state["power_writes"].append((address, value))
        elif 0xFC088340 <= address <= 0xFC088740:
            state["current_burst"].append(value & 0xFF)
        elif address == 0xFC088E00 and state["current_burst"]:
            state["seq_bursts"].append(bytes(state["current_burst"]))
            state["seq_run_modes"].append(value)
            state["current_burst"].clear()
        elif address == ISP0 and value == 3:
            assert state["armed"] == state["triggered"]
            assert state["dma_start_flip"] is None
            assert len(state["seq_bursts"]) == 4 + 3 * (state["armed"] + 1)
            assert [len(burst) for burst in state["seq_bursts"][-3:]] == [251, 45, 124]
            assert state["seq_run_modes"][-3:] == [2, 2, 0]
            assert struct.unpack("<4I", uc.mem_read(ISP0 + 0x20, 16)) == (
                RAW_BASE, STRIDE_PIXELS * 2, 0, LIVE_HEIGHT - 1,
            )
            assert struct.unpack("<2I", uc.mem_read(RAW_BASE + 0x60000000 + RAW_BYTES - 8, 8)) == (
                0xC0DEBFAD, 0x3F214052,
            )
            state["armed"] += 1
        elif address == 0xFC0A1210 and value == 1 and state["armed"] > state["triggered"]:
            assert len(state["seq_bursts"][-1]) == 124
            state["triggered"] += 1
            if not args.no_dma:
                state["dma_start_flip"] = state["flips"]
        elif address == ISP0 + 4 and (value & (1 << 30)):
            state["stopped"] = True
            state["dma_start_flip"] = None
        elif address == 0xF3441300 and (value & 3) == 3 and state["l2_syncs"] >= 2:
            state["flips"] += 1
            cur_pa = struct.unpack("<I", uc.mem_read(0xF3441320, 4))[0]
            va = cur_pa + 0x60000000
            if 11 <= state["flips"] <= 21:
                pixels = tuple(struct.unpack("<H", uc.mem_read(va + (y * 640 + 320) * 2, 2))[0]
                               for y in (150, 360))
                state["lcd_frame_pairs"].append(pixels)
            if state["flips"] >= (41 if args.no_dma else 21):
                banner_px = struct.unpack("<H", uc.mem_read(va, 2))[0]
                if banner_px == 0x124F:
                    state["returned_to_status"] = True
                    uc.emu_stop()

    cpu.hook_add(UC_HOOK_MEM_READ, on_read)
    cpu.hook_add(UC_HOOK_MEM_WRITE, on_write)
    cpu.reg_write(UC_ARM_REG_CPSR, 0xD3)
    cpu.reg_write(UC_ARM_REG_R0, context)
    cpu.reg_write(UC_ARM_REG_SP, stack + 0x2000)
    cpu.reg_write(UC_ARM_REG_LR, stop)
    cpu.emu_start(base + entry, stop, count=200000000)

    assert struct.unpack("<I", cpu.mem_read(arena + 0x7000 + 28, 4))[0] == PROBE_OK
    assert len(state["power_writes"]) >= 20, len(state["power_writes"])
    assert (0xFC02A0D0, 0xAAAAAA) in state["power_writes"]
    if args.no_dma:
        assert state["armed"] == state["triggered"] == 1
        assert state["timeout_snapshot"] == 3
        assert struct.unpack("<I", cpu.mem_read(ISP0, 4)) == (2,)
        assert state["returned_to_status"]
        print("Verified BayerRAW timeout captures the armed writer state before cleanup and returns to the shell.")
        return

    assert state["armed"] == state["triggered"] >= 3
    bursts = state["seq_bursts"]
    assert [len(b) for b in bursts] == [37, 37, 25, 169] + [251, 45, 124] * state["armed"]
    assert bursts[4:] == bursts[4:7] * state["armed"]
    for index in (RAW_BASE >> 20, (RAW_BASE >> 20) + 0x600):
        assert struct.unpack("<I", cpu.mem_read(arena + index * 4, 4))[0] == RAW_BASE | 0x11402
    assert struct.unpack("<I", cpu.mem_read(0xF290E004, 4))[0] == 0
    assert struct.unpack("<I", cpu.mem_read(0xF290E008, 4))[0] == 0
    assert (struct.unpack("<I", cpu.mem_read(0xF0105138, 4))[0] & 0x300) == 0x300
    assert (struct.unpack("<I", cpu.mem_read(0xF0105068, 4))[0] & 0x10000) == 0
    assert struct.unpack("<I", cpu.mem_read(0xFC020028, 4))[0] == 0xBB
    assert struct.unpack("<I", cpu.mem_read(0xFC020134, 4))[0] == 0x37
    assert struct.unpack("<I", cpu.mem_read(0xFC021000, 4))[0] == 0x111
    assert struct.unpack("<I", cpu.mem_read(0xFC021008, 4))[0] == 1
    assert struct.unpack("<I", cpu.mem_read(0xFC021024, 4))[0] == 0x0005A783
    assert struct.unpack("<I", cpu.mem_read(0xFC029028, 4))[0] == 0x7E
    assert struct.unpack("<I", cpu.mem_read(0xFC02A064, 4))[0] == 0x1111
    assert struct.unpack("<I", cpu.mem_read(0xFC02D000, 4))[0] == 3
    assert struct.unpack("<I", cpu.mem_read(0xFC0A1100, 4))[0] == 1
    assert struct.unpack("<I", cpu.mem_read(0xFC0A1120, 4))[0] == 0x04EB1033
    assert struct.unpack("<I", cpu.mem_read(0xFC0A114C, 4))[0] == 4
    assert struct.unpack("<I", cpu.mem_read(0xFC0A1150, 4))[0] == 0x00250005
    assert struct.unpack("<I", cpu.mem_read(0xFC0A1110, 4))[0] == 1
    assert struct.unpack("<I", cpu.mem_read(0xFC080020, 4))[0] == 0x00FFFFF0
    assert struct.unpack("<I", cpu.mem_read(0xFC0F0000, 4))[0] == 0x0103FFFF
    assert struct.unpack("<I", cpu.mem_read(0xFC0F0050, 4))[0] == 1
    assert struct.unpack("<I", cpu.mem_read(0xFC0F0150, 4))[0] == 1
    assert struct.unpack("<I", cpu.mem_read(0xFC0A1354, 4))[0] == 0x05F51024
    assert struct.unpack("<I", cpu.mem_read(0xFC0A13D0, 4))[0] == 0x0D200000
    assert struct.unpack("<I", cpu.mem_read(0xFC0A1454, 4))[0] == 0x05E7100F
    pairs = state["lcd_frame_pairs"]
    assert pairs[1:] == [
        (0x000F, 0x000F), (0x000F, 0x000F),
        (0xF00F, 0x00FF), (0xF00F, 0x00FF),
        (0x00FF, 0xF00F), (0x00FF, 0xF00F),
        (0xF00F, 0x00FF), (0xF00F, 0x00FF),
        (0xF00F, 0x00FF), (0xF00F, 0x00FF),
    ], pairs
    assert state["stopped"]
    assert state["returned_to_status"]
    print("Verified BayerRAW mode: mode-0x37 timing, repeated ISP0 arms and modeled DMA completion, software LCD reconstruction, and stop.")


if __name__ == "__main__":
    main()
