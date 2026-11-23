"""Verify the ZVOS shell: GIC IRQ dispatch, 8x8 font rendering, mode switching, and allocators."""
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
from encode_bad_apple import encode_frames

HANDOFF_MAGIC = int.from_bytes(b"ZVRH", "little")
PROBE_OK = 0x4F4B5254
ARENA_BYTES = 0x10000
FRAME_BYTES = 614400


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    image = args.image.read_bytes()
    magic, version, header_bytes, code_bytes, entry, checksum, flags, reserved = HEADER.unpack_from(image)
    code = image[header_bytes:]
    assert (magic, version, header_bytes, flags, reserved) == (MAGIC, VERSION, 32, 1, 0)
    assert code_bytes == len(code) and zlib.crc32(code) == checksum

    row_bytes = 320 // 8
    clip = encode_frames([b"\xFF" * (row_bytes * 240), b"\x00" * (row_bytes * 240)], 320, 240, 24)

    cpu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    base, context, stack, arena, stop = 0x5F100000, 0x5F200000, 0x5F300000, 0x65000000, 0x5F400000
    frame_pa = 0x22C48000
    frame_va = frame_pa + 0x60000000
    clip_src_va, clip_dst_va = 0x5C000000, 0x84000000
    clip_map = (len(clip) + 0xFFF) & ~0xFFF

    for start, size in (
        (base, (len(code) + 0xFFF) & ~0xFFF),
        (context, 0x1000),
        (stack, 0x2000),
        (arena, ARENA_BYTES),
        (stop, 0x1000),
        (0x81000000, 0x200000),
        (0x81E00000, 0x200000),
        (0x85000000, 0x300000),
        (0x86000000, 0x100000),
        (clip_src_va, clip_map),
        (clip_dst_va, clip_map),
        (0x64419000, 0x3000),
        (0x643EB000, 0x1000),
        (frame_va & ~0xFFF, (FRAME_BYTES + 0x2000) & ~0xFFF),
        (0xF2403000, 0x1000),
        (0xF2406000, 0x1000),
        (0xF2407000, 0x1000),
        (0xF2910000, 0x1000),
        (0xF3440000, 0x7000),
        (0xF0000000, 0x1000),
        (0xF0010000, 0x1000),
        (0xF0030000, 0x1000),
        (0xF8000000, 0x3000),
    ):
        cpu.mem_map(start, size)

    cpu.mem_write(base, code)
    cpu.mem_write(clip_src_va, clip)
    handoff = [
        HANDOFF_MAGIC, VERSION, 48, 7, arena, 0x05000000, ARENA_BYTES,
        0, 0x02000800, FRAME_BYTES, clip_src_va, len(clip),
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
    state = {"tick": 1000, "l2_syncs": 0, "flips": 0, "frames": {}, "menu": {}, "addresses": {}}
    adc0_base, adc1_base = 0xF2406000, 0xF2407000
    adc_data = {
        adc1_base + 0x14: (1, 0),
        adc1_base + 0x20: (1, 3),
    }
    adc_started = {0: None, 1: None}
    adc_reads = {}

    def key_value(ctrl, channel, flip):
        if ctrl == 1 and channel == 0:
            return 0x000 if flip in (7, 8) else 0x3FF  # DELETE on B0
        if flip in (4, 5, 6, 7, 8, 9, 10, 19, 20):
            return 0x000
        if flip in (2, 17, 18):
            return 0x2AD  # Right on the camera.
        if flip in (15, 16):
            return 0x15F  # Up on the camera.
        if flip in (11, 12):
            return 0x1FA  # Down on the camera.
        return 0x3FF

    def on_read(uc, _access, address, _size, _val, _ud):
        if address == 0xF240310C:
            state["tick"] += 35000
            uc.mem_write(address, struct.pack("<I", state["tick"]))
        elif address == 0xF80027BC:
            uc.mem_write(address, struct.pack("<I", 0))
        elif address in (adc0_base + 0x10, adc1_base + 0x10) or address in adc_data:
            flip = state["flips"]
            if address in (adc0_base + 0x10, adc1_base + 0x10):
                ctrl = 0 if address == adc0_base + 0x10 else 1
                started = adc_started[ctrl]
                stuck = ctrl == 1 and flip == 9 and started is not None and started[0] == flip
                uc.mem_write(address, struct.pack("<H", 0x11 if stuck else 0))
            else:
                ctrl, channel = adc_data[address]
                started_flip, started_tick, selected_channel = adc_started[ctrl]
                assert started_flip == flip and state["tick"] - started_tick >= 50
                assert not (ctrl == 1 and flip == 9), "Read stale ADC data after timeout"
                assert channel == selected_channel
                k = (ctrl, channel, flip)
                adc_reads[k] = adc_reads.get(k, 0) + 1
                val = key_value(ctrl, channel, flip)
                if ctrl == 1 and channel == 3 and flip == 2 and adc_reads[k] == 2:
                    val = 0x0D4  # Reject a pair spanning Right and Left.
                uc.mem_write(address, struct.pack("<H", val))
        elif address == 0xF3441300 and state["l2_syncs"] >= 2:
            uc.mem_write(address, struct.pack("<I", 2))
        elif address == 0xF3441304:
            cur = struct.unpack("<I", uc.mem_read(address, 4))[0]
            if cur & 0x40000000:
                uc.mem_write(address, struct.pack("<I", cur & ~0x80000000))

    def on_write(uc, _access, address, _size, value, _ud):
        assert not 0xF2406000 <= address < 0xF2407000, "Unexpected ADC0 write"
        if address == adc1_base + 4 and value == 1:
            selected, = struct.unpack("<H", uc.mem_read(adc1_base, 2))
            assert selected in (1 << 0, 1 << 3), f"Expected ADC1 ch 0 or 3, got {selected:#x}"
            adc_started[1] = (state["flips"], state["tick"], selected.bit_length() - 1)
        elif address == 0xF8002730:
            state["l2_syncs"] += 1
            uc.mem_write(0xF8002730, struct.pack("<I", 0))
        elif address == 0xF3441300 and (value & 3) == 3 and state["l2_syncs"] >= 2:
            state["flips"] += 1
            if state["flips"] >= 2:
                cur_pa = struct.unpack("<I", uc.mem_read(0xF3441320, 4))[0]
                va = cur_pa + 0x60000000
                px = struct.unpack("<H", uc.mem_read(va, 2))[0]
                state["frames"][state["flips"]] = px
                state["addresses"][state["flips"]] = cur_pa
                if px == 0x124F:
                    yellow = struct.pack("<H", 0xFF0F)
                    selected = []
                    for row in (88, 120):
                        glyph = b"".join(uc.mem_read(va + (y * 640 + 32) * 2, 32)
                                         for y in range(row, row + 16))
                        selected.append(yellow in glyph)
                    state["menu"][state["flips"]] = tuple(selected)
                if state["flips"] == 29:
                    uc.emu_stop()

    cpu.hook_add(UC_HOOK_MEM_READ, on_read)
    cpu.hook_add(UC_HOOK_MEM_WRITE, on_write)
    cpu.reg_write(UC_ARM_REG_CPSR, 0xD3)
    cpu.reg_write(UC_ARM_REG_R0, context)
    cpu.reg_write(UC_ARM_REG_SP, stack + 0x2000)
    cpu.reg_write(UC_ARM_REG_LR, stop)
    cpu.emu_start(base + entry, stop, count=100000000)

    result_word = struct.unpack("<I", cpu.mem_read(arena + 0x7000 + 28, 4))[0]
    assert result_word == PROBE_OK, hex(result_word)
    assert struct.unpack("<I", cpu.mem_read(0xF8000100, 4))[0] == 1
    assert struct.unpack("<I", cpu.mem_read(0xF8001000, 4))[0] == 1
    frames = state["frames"]
    menu = state["menu"]
    assert [frames.get(i) for i in (2, 7, 10, 11, 22)] == [0x124F, 0x000F, 0x124F, 0x124F, 0xFFFF], frames
    assert [menu.get(i) for i in (4, 14, 15, 16, 17, 19)] == [
        (True, False), (False, True), (False, True), (False, True), (True, False), (False, True),
    ], menu
    assert (1, 3, 9) not in adc_reads
    assert [frames[i] for i in range(22, 30)] == [
        0xFFFF, 0xFFFF, 0xFFFF, 0x000F, 0x000F, 0xFFFF, 0xFFFF, 0x000F,
    ], frames
    addresses = state["addresses"]
    assert addresses[22] == addresses[23] == addresses[24] == addresses[27] == addresses[28]
    assert addresses[25] == addresses[26] == addresses[29] != addresses[22]
    print(f"Verified ZVOS shell ({len(code)} bytes): input, mode navigation and 24 fps playback on 50 Hz scanout.")


if __name__ == "__main__":
    main()
