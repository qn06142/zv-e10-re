"""Exercise the RTOS 640x480 procedural fire image across multiple animation frames in Unicorn."""
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

from build_rtos import HEADER, MAGIC, VERSION, package_image

HANDOFF_MAGIC = int.from_bytes(b"ZVRH", "little")
PROBE_OK = 0x4F4B5254
ARENA_BYTES = 0x10000
FRAME_BYTES = 614400
FIRE_PALETTE = {
    0x000F, 0x200F, 0x400F, 0x600F, 0x810F, 0xA10F, 0xC20F, 0xE30F,
    0xF40F, 0xF50F, 0xF70F, 0xF90F, 0xFB1F, 0xFD4F, 0xFF9F, 0xFFFF,
}


def run_fire_case(
    code,
    entry,
    *,
    slot_va=0x6441B27C,
    frame_pa=0x22C48000,
    cur_dma=0x22C84E80,
    pl310_ctrl=1,
    target_frames=6,
    clip_data=b"",
):
    cpu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    base, context, stack, arena, stop = 0x03100000, 0x02000000, 0x02100000, 0x65000000, 0x02300000
    clip_src_va, clip_dst_va = 0x5C000000, 0x84000000
    frame_va = (frame_pa + 0x60000000) & 0xFFFFFFFF

    regions = [
        (base, 0x2000),
        (context, 0x1000),
        (stack, 0x2000),
        (arena, ARENA_BYTES),
        (stop, 0x1000),
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
    ]
    if clip_data:
        aligned_clip = (len(clip_data) + 0xFFF) & ~0xFFF
        regions.extend([(clip_src_va, aligned_clip), (clip_dst_va, aligned_clip)])
    for start, size in regions:
        cpu.mem_map(start, size)

    cpu.mem_write(base, code)
    if clip_data:
        cpu.mem_write(clip_src_va, clip_data)
    flags = 3 | (4 if clip_data else 0)
    handoff = [
        HANDOFF_MAGIC,
        VERSION,
        48,
        flags,
        arena,
        0x05000000,
        ARENA_BYTES,
        0,
        0x02000800,
        FRAME_BYTES,
        clip_src_va if clip_data else 0,
        len(clip_data),
    ]
    cpu.mem_write(context, HEADER.pack(*handoff[:8]) + struct.pack("<4I", *handoff[8:]))
    for ch in range(0x39, 0x41):
        cpu.mem_write(0x643EB19C + ch * 4, struct.pack("<I", 0x22B))
    desc = [frame_pa, 0x01E00280, 0, 0x01E00280, 0, 0, 0, 0, 0, 0, 1, 0x5F04001E, 0x63733989, 0]
    cpu.mem_write(slot_va, struct.pack("<14I", *desc))

    cpu.mem_write(0xF3445000, struct.pack("<I", 0x00010114))
    cpu.mem_write(0xF3446000, struct.pack("<I", 0x00000000))
    cpu.mem_write(0xF3440144, struct.pack("<I", 0x02000233))
    cpu.mem_write(0xF3440404, struct.pack("<I", 0x00000000))
    cpu.mem_write(0xF344042C, struct.pack("<I", 0x000001E0))
    cpu.mem_write(0xF3441300, struct.pack("<I", 0x00000003))
    cpu.mem_write(0xF3441304, struct.pack("<I", 0x80000000))
    cpu.mem_write(0xF3441310, struct.pack("<I", cur_dma))
    cpu.mem_write(0xF8002100, struct.pack("<I", pl310_ctrl))
    # Simulate active GIC, XDMAC, and DMA330 thread 2 + manager before quiesce_platform.
    cpu.mem_write(0xF8000100, struct.pack("<I", 1))
    cpu.mem_write(0xF8001000, struct.pack("<I", 1))
    cpu.mem_write(0xF0000018, struct.pack("<I", 1))
    cpu.mem_write(0xF0010018, struct.pack("<I", 1))
    cpu.mem_write(0xF0030000, struct.pack("<I", 1))
    cpu.mem_write(0xF0030110, struct.pack("<I", 1))

    state = {
        "tick": 1000,
        "l2_syncs": 0,
        "led_toggles": 0,
        "osd_starts": 0,
        "dma330_kills": [],
        "snapshots": [],
    }

    def on_read(uc, _access, address, _size, _val, _ud):
        if address == 0xF240310C:
            state["tick"] += 35000
            uc.mem_write(address, struct.pack("<I", state["tick"]))
        elif address == 0xF3441300:
            result_val = struct.unpack("<I", uc.mem_read(arena + 0x7000 + 28, 4))[0]
            if result_val == PROBE_OK:
                uc.mem_write(address, struct.pack("<I", 2))
        elif address == 0xF3441304:
            cur = struct.unpack("<I", uc.mem_read(address, 4))[0]
            if cur & 0x40000000:
                uc.mem_write(address, struct.pack("<I", cur & ~0x80000000))
        elif address == 0xF3441310:
            result_val = struct.unpack("<I", uc.mem_read(arena + 0x7000 + 28, 4))[0]
            if result_val in (7, PROBE_OK):
                uc.mem_write(address, struct.pack("<I", frame_pa + 0x1000))

    def on_write(uc, _access, address, _size, value, _ud):
        if address == 0xF8002730:
            state["l2_syncs"] += 1
            uc.mem_write(0xF8002730, struct.pack("<I", 0))
            if state["l2_syncs"] > 1:
                bot = bytes(uc.mem_read(frame_va + 472 * 1280, 1280))
                mid = bytes(uc.mem_read(frame_va + 360 * 1280, 1280))
                state["snapshots"].append((bot, mid))
                if len(state["snapshots"]) >= target_frames:
                    uc.emu_stop()
        elif address == 0xF3441300 and (value & 3) == 3:
            state["osd_starts"] += 1
        elif address == 0xF0030D04 and value == 0:
            state["dma330_kills"].append(struct.unpack("<I", uc.mem_read(0xF0030D08, 4))[0])
        elif address in (0xF2910048, 0xF2910044):
            state["led_toggles"] += 1

    cpu.hook_add(UC_HOOK_MEM_READ, on_read)
    cpu.hook_add(UC_HOOK_MEM_WRITE, on_write)
    cpu.reg_write(UC_ARM_REG_CPSR, 0xD3)
    cpu.reg_write(UC_ARM_REG_R0, context)
    cpu.reg_write(UC_ARM_REG_SP, stack + 0x2000)
    cpu.reg_write(UC_ARM_REG_LR, stop)
    cpu.emu_start(base + entry, stop, count=20000000)

    result_word = struct.unpack("<I", cpu.mem_read(arena + 0x7000 + 28, 4))[0]
    return cpu, arena, frame_va, state, result_word


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    image = args.image.read_bytes()
    magic, version, header_bytes, code_bytes, entry, checksum, flags, reserved = HEADER.unpack_from(image)
    code = image[header_bytes:]
    assert (magic, version, header_bytes, flags, reserved) == (MAGIC, VERSION, 32, 1, 0)
    assert code_bytes == len(code) and zlib.crc32(code) == checksum
    assert package_image(code, entry, display=True) == image

    cpu, arena, frame_va, state, result = run_fire_case(code, entry, target_frames=7)
    assert result == PROBE_OK, hex(result)
    assert len(state["snapshots"]) == 7, state["snapshots"]
    assert state["l2_syncs"] == 8 and state["led_toggles"] >= 1, state
    assert state["dma330_kills"] == [0x00010201, 0x00000001], state["dma330_kills"]
    l1 = struct.unpack("<4096I", cpu.mem_read(arena, 0x4000))
    assert l1[0x000] == 0x0001140E and l1[0x3FF] == 0x3FF1140E and l1[0x400] == 0
    assert l1[0x600] == 0x0001140E and l1[0x9FF] == 0x3FF1140E
    assert l1[0xF00] == 0xF0000406 and l1[0xF80] == 0xF8000406 and l1[0xFFF] == 0xFFF00406
    assert struct.unpack("<I", cpu.mem_read(0xF8000100, 4))[0] == 0
    assert struct.unpack("<I", cpu.mem_read(0xF8001000, 4))[0] == 0
    assert struct.unpack("<I", cpu.mem_read(0xF0000018, 4))[0] == 0
    assert struct.unpack("<I", cpu.mem_read(0xF0010018, 4))[0] == 0
    assert struct.unpack("<I", cpu.mem_read(0xF003002C, 4))[0] == 0xFFFFFFFF

    # Verify all pixels in row 472 and row 360 belong to the RGBA4444 fire palette and frames evolve.
    for bot, mid in state["snapshots"]:
        bot_px = set(struct.unpack("<640H", bot))
        mid_px = set(struct.unpack("<640H", mid))
        assert bot_px <= FIRE_PALETTE and mid_px <= FIRE_PALETTE, (bot_px - FIRE_PALETTE, mid_px - FIRE_PALETTE)
    assert state["snapshots"][0][0] != state["snapshots"][1][0], "Bottom emitter row did not update"
    assert state["snapshots"][0][1] != state["snapshots"][5][1], "Mid flame row did not evolve"

    # Verify optional clip.bin staging copy from vmalloc VA into 0x84000000 (DDR0 PA 0x24000000).
    sample_clip = bytes((i * 13) & 0xFF for i in range(4096 + 37))
    clip_cpu, _, _, _, clip_result = run_fire_case(code, entry, target_frames=2, clip_data=sample_clip)
    assert clip_result == PROBE_OK, hex(clip_result)
    assert bytes(clip_cpu.mem_read(0x84000000, len(sample_clip))) == sample_clip, "Clip staging copy mismatch"

    print(
        f"Verified packaged 640x480 fire image across {len(state['snapshots'])} frames, "
        f"PL310 syncs={state['l2_syncs']}, LED toggles={state['led_toggles']}, clip staging, and pixel evolution."
    )


if __name__ == "__main__":
    main()
