"""Verify the Bad Apple!! bare-metal C player against synthetic ZVBA frames in Unicorn."""
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


def make_test_clip():
    row_bytes = 640 // 8
    f0 = b"\xFF" * (row_bytes * 480)  # all white
    f1 = b"\x00" * (row_bytes * 480)  # all black
    f2 = (b"\xF0" * row_bytes) * 480  # vertical stripes
    return encode_frames([f0, f1, f2], 640, 480, 24)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    image = args.image.read_bytes()
    magic, version, header_bytes, code_bytes, entry, checksum, flags, reserved = HEADER.unpack_from(image)
    code = image[header_bytes:]
    assert (magic, version, header_bytes, flags, reserved) == (MAGIC, VERSION, 32, 1, 0)
    assert code_bytes == len(code) and zlib.crc32(code) == checksum

    clip = make_test_clip()

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
        (0x85000000, 0x200000),
        (clip_src_va, clip_map),
        (clip_dst_va, clip_map),
        (0x64419000, 0x3000),
        (0x643EB000, 0x1000),
        (frame_va & ~0xFFF, (FRAME_BYTES + 0x2000) & ~0xFFF),
        (0xF2403000, 0x1000),
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

    state = {"tick": 1000, "l2_syncs": 0, "flips": 0, "last_pa": None, "rows": []}

    def on_read(uc, _access, address, _size, _val, _ud):
        if address == 0xF240310C:
            state["tick"] += 35000
            uc.mem_write(address, struct.pack("<I", state["tick"]))
        elif address == 0xF80027BC:
            uc.mem_write(address, struct.pack("<I", 0))
        elif address == 0xF3441300 and state["l2_syncs"] >= 2:
            uc.mem_write(address, struct.pack("<I", 2))
        elif address == 0xF3441304:
            cur = struct.unpack("<I", uc.mem_read(address, 4))[0]
            if cur & 0x40000000:
                uc.mem_write(address, struct.pack("<I", cur & ~0x80000000))

    def on_write(uc, _access, address, _size, value, _ud):
        if address == 0xF8002730:
            state["l2_syncs"] += 1
            uc.mem_write(0xF8002730, struct.pack("<I", 0))
        elif address == 0xF3441300 and (value & 3) == 3 and state["l2_syncs"] >= 2:
            state["flips"] += 1
            if state["flips"] >= 2:
                cur_pa = struct.unpack("<I", uc.mem_read(0xF3441320, 4))[0]
                if cur_pa != state["last_pa"]:
                    state["last_pa"] = cur_pa
                    px8 = struct.unpack("<8H", uc.mem_read(cur_pa + 0x60000000, 16))
                    state["rows"].append(px8)
                    if len(state["rows"]) >= 3:
                        uc.emu_stop()

    cpu.hook_add(UC_HOOK_MEM_READ, on_read)
    cpu.hook_add(UC_HOOK_MEM_WRITE, on_write)
    cpu.reg_write(UC_ARM_REG_CPSR, 0xD3)
    cpu.reg_write(UC_ARM_REG_R0, context)
    cpu.reg_write(UC_ARM_REG_SP, stack + 0x2000)
    cpu.reg_write(UC_ARM_REG_LR, stop)
    cpu.emu_start(base + entry, stop, count=40000000)

    result_word = struct.unpack("<I", cpu.mem_read(arena + 0x7000 + 28, 4))[0]
    assert result_word == PROBE_OK, hex(result_word)
    assert state["rows"][0] == (0xFFFF,) * 8, state["rows"][0]
    assert state["rows"][1] == (0x000F,) * 8, state["rows"][1]
    assert state["rows"][2] == (0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0x000F, 0x000F, 0x000F, 0x000F), state["rows"][2]
    print(f"Verified Bad Apple player ({len(code)} bytes): 3 ZVBA frames decoded to exact RGBA4444 pixels.")


if __name__ == "__main__":
    main()
