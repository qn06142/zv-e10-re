"""Exercise the C bare-metal runtime (crt0, .rodata/.data/.bss, heap, MMU, OSD0) in Unicorn."""
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
DISPLAY_PA = 0x25000000
DISPLAY_VA = 0x85000000
DISPLAY_SIZE = 0x00200000
FLIP_COLORS = [0x0F0F, 0x00FF, 0xFFFF, 0xF00F]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
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
    clip_src_va, clip_dst_va = 0x5C000000, 0x84000000
    sample_clip = bytes((i * 7) & 0xFF for i in range(4096 + 17))

    for start, size in (
        (base, (len(code) + 0xFFF) & ~0xFFF),
        (context, 0x1000),
        (stack, 0x2000),
        (arena, ARENA_BYTES),
        (stop, 0x1000),
        (0x81000000, 0x200000),   # Relocated C image + .bss
        (0x81E00000, 0x200000),   # C stack below 0x82000000
        (DISPLAY_VA, DISPLAY_SIZE),
        (DISPLAY_VA + DISPLAY_SIZE, 0x1000),  # Bump heap scratch
        (clip_src_va, 0x2000),
        (clip_dst_va, 0x2000),
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
    cpu.mem_write(clip_src_va, sample_clip)
    handoff = [
        HANDOFF_MAGIC, VERSION, 48, 7, arena, 0x05000000, ARENA_BYTES,
        0, 0x02000800, FRAME_BYTES, clip_src_va, len(sample_clip),
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

    state = {"tick": 1000, "l2_syncs": 0, "colors": [], "first_flip_ticks": 0,
             "scanout": None, "flips": [], "ready": False, "initialized": False}

    def on_read(uc, _access, address, _size, _val, _ud):
        if address == 0xF240310C:
            state["tick"] += 35000
            uc.mem_write(address, struct.pack("<I", state["tick"]))
            if state["initialized"] and not state["flips"]:
                state["first_flip_ticks"] += 1
        elif address == 0xF3441300:
            if state["initialized"] and (state["first_flip_ticks"] >= 3 or state["flips"]):
                uc.mem_write(address, struct.pack("<I", 2))
                state["ready"] = True
        elif address == 0xF80027BC:
            uc.mem_write(address, struct.pack("<I", 0))
        elif address == 0xF3441304:
            cur = struct.unpack("<I", uc.mem_read(address, 4))[0]
            if cur & 0x40000000:
                uc.mem_write(address, struct.pack("<I", cur & ~0x80000000))

    def on_write(uc, _access, address, _size, value, _ud):
        if address == 0xF80027BC:
            uc.mem_write(0xF80027BC, struct.pack("<I", 0))
        elif address == 0xF8002730:
            uc.mem_write(0xF8002730, struct.pack("<I", 0))
            if state["initialized"]:
                state["l2_syncs"] += 1
        elif address == 0xF3441320:
            if state["initialized"]:
                assert state["ready"], "Scanout address written while channel remained busy"
                assert value != state["scanout"]
            state["scanout"] = value
        elif address == 0xF3441300 and value == 3:
            if not state["initialized"]:
                assert state["scanout"] == DISPLAY_PA
                assert bytes(uc.mem_read(DISPLAY_VA, FRAME_BYTES)) == struct.pack("<H", 0xF00F) * (FRAME_BYTES // 2)
                state["initialized"] = True
                return
            assert state["ready"], "Scanout rearmed while channel remained busy"
            state["ready"] = False
            scanout = state["scanout"]
            if not state["flips"] or state["flips"][-1] != scanout:
                state["flips"].append(scanout)
                va = scanout + 0x60000000
                first, = struct.unpack("<H", uc.mem_read(va, 2))
                assert bytes(uc.mem_read(va, FRAME_BYTES)) == struct.pack("<H", first) * (FRAME_BYTES // 2)
                state["colors"].append(first)
                if len(state["flips"]) == len(FLIP_COLORS):
                    uc.emu_stop()

    cpu.hook_add(UC_HOOK_MEM_READ, on_read)
    cpu.hook_add(UC_HOOK_MEM_WRITE, on_write)
    cpu.reg_write(UC_ARM_REG_CPSR, 0xD3)
    cpu.reg_write(UC_ARM_REG_R0, context)
    cpu.reg_write(UC_ARM_REG_SP, stack + 0x2000)
    cpu.reg_write(UC_ARM_REG_LR, stop)
    cpu.emu_start(base + entry, stop, count=20000000)

    result_word = struct.unpack("<I", cpu.mem_read(arena + 0x7000 + 28, 4))[0]
    assert result_word == PROBE_OK, hex(result_word)
    assert struct.unpack("<I", cpu.mem_read(DISPLAY_VA + DISPLAY_SIZE, 4))[0] == 0xCAFEBABE
    assert bytes(cpu.mem_read(clip_dst_va, len(sample_clip))) == sample_clip
    for va_base in (DISPLAY_PA, DISPLAY_VA):
        for section, attributes in ((-1, 0x1140E), (0, 0x11402), (1, 0x11402), (15, 0x11402), (16, 0x1140E)):
            va = va_base + section * 0x100000
            expected = DISPLAY_PA + section * 0x100000 | attributes
            assert struct.unpack("<I", cpu.mem_read(arena + (va >> 20) * 4, 4))[0] == expected
    assert not any(cpu.mem_read(frame_va, FRAME_BYTES)), "Stock framebuffer was modified"
    assert state["first_flip_ticks"] >= 3
    assert state["l2_syncs"] == 0, "Runtime used per-frame cache maintenance"
    assert state["flips"] == [DISPLAY_PA + FRAME_BYTES, DISPLAY_PA] * 2
    assert state["colors"] == FLIP_COLORS, [hex(c) for c in state["colors"]]
    print(f"Verified C runtime ({len(code)} bytes): busy flip retried, four full-buffer colors, heap and clip OK.")


if __name__ == "__main__":
    main()
