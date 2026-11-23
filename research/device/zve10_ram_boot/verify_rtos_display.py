"""Exercise the RTOS full-LCD display image in Unicorn across primary/secondary slots and failure guards."""
import argparse
import struct
import zlib
from pathlib import Path

from unicorn import UC_ARCH_ARM, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_MODE_ARM, Uc
from unicorn.arm_const import (
    UC_ARM_REG_CPSR,
    UC_ARM_REG_LR,
    UC_ARM_REG_PC,
    UC_ARM_REG_R0,
    UC_ARM_REG_SP,
)

from build_rtos import HEADER, MAGIC, VERSION, package_image

HANDOFF_MAGIC = int.from_bytes(b"ZVRH", "little")
PROBE_OK = 0x4F4B5254
ARENA_BYTES = 0x4000
FRAME_BYTES = 614400
PALETTE = (0xFFFF, 0xFF0F, 0x0FFF, 0x0F0F, 0xF0FF, 0xF00F, 0x00FF, 0x000F)


def run_display_case(
    code,
    entry,
    *,
    base=0x03100000,
    slot_va=0x6441B27C,
    frame_pa=0x22C48000,
    cur_dma=0x22C84E80,
    pl310_ctrl=1,
    rearm_on_recheck=False,
    mutate_handoff=None,
    bad_slot=False,
):
    cpu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    context, stack, arena, stop = 0x02000000, 0x02100000, 0x02200000, 0x02300000
    frame_va = (frame_pa + 0x60000000) & 0xFFFFFFFF

    # Map code, context, stack, arena, stop, descriptor page, AIF table page, framebuffer, and MMIO.
    for start, size in (
        (base & ~0xFFF, 0x2000),
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
        (0xF8002000, 0x1000),
    ):
        cpu.mem_map(start, size)

    cpu.mem_write(base, code)
    handoff = [HANDOFF_MAGIC, VERSION, 40, 3, arena, 0x05000000, ARENA_BYTES, 0, 0x02000800, FRAME_BYTES]
    if mutate_handoff:
        handoff[mutate_handoff[0]] = mutate_handoff[1]
    cpu.mem_write(context, HEADER.pack(*handoff[:8]) + struct.pack("<2I", *handoff[8:]))

    # Initialize AIF mode table sentinel 0x22b at 0x643eb19c + 4*ch for ch 0x39..0x40.
    for ch in range(0x39, 0x41):
        cpu.mem_write(0x643EB19C + ch * 4, struct.pack("<I", 0x22B))

    # Populate primary or secondary Route 1 OSD0 descriptor.
    if not bad_slot:
        desc = [frame_pa, 0x01E00280, 0, 0x01E00280, 0, 0, 0, 0, 0, 0, 1, 0x5F04001E, 0x63733989, 0]
        cpu.mem_write(slot_va, struct.pack("<14I", *desc))

    # Initialize VPH / OSD0 / PL310 MMIO state matching Senser.
    cpu.mem_write(0xF3445000, struct.pack("<I", 0x00010114))
    cpu.mem_write(0xF3446000, struct.pack("<I", 0x00000000))
    cpu.mem_write(0xF3440144, struct.pack("<I", 0x02000233))
    cpu.mem_write(0xF3440404, struct.pack("<I", 0x00000000))
    cpu.mem_write(0xF344042C, struct.pack("<I", 0x000001E0))
    cpu.mem_write(0xF3441300, struct.pack("<I", 0x00000003))
    cpu.mem_write(0xF3441304, struct.pack("<I", 0x80000000))
    cpu.mem_write(0xF3441310, struct.pack("<I", cur_dma))
    cpu.mem_write(0xF8002100, struct.pack("<I", pl310_ctrl))

    state = {"tick": 1000, "l2_cleans": 0, "l2_syncs": 0, "heartbeats": 0, "rearmed": False}

    def on_read(uc, _access, address, _size, _val, _ud):
        if address == 0xF240310C:
            state["tick"] += 15000
            uc.mem_write(address, struct.pack("<I", state["tick"]))
        elif address == 0xF3441304:
            cur = struct.unpack("<I", uc.mem_read(address, 4))[0]
            if cur & 0x40000000:
                uc.mem_write(address, struct.pack("<I", cur & ~0x80000000))
        elif address == 0xF3441300 and rearm_on_recheck and not state["rearmed"]:
            # Rearm bit 0 after drain once idle_recheck reads it.
            result_val = struct.unpack("<I", uc.mem_read(context + 28, 4))[0]
            if result_val == 5 and state["tick"] > 40000:
                uc.mem_write(0xF3441300, struct.pack("<I", 1))
                state["rearmed"] = True
        elif address == 0xF3441310:
            result_val = struct.unpack("<I", uc.mem_read(context + 28, 4))[0]
            if result_val == 7:
                uc.mem_write(address, struct.pack("<I", frame_pa + 0x1000))

    def on_write(uc, _access, address, _size, value, _ud):
        if address == 0xF80027B0:
            state["l2_cleans"] += 1
        elif address == 0xF8002730:
            state["l2_syncs"] += 1
            uc.mem_write(0xF8002730, struct.pack("<I", 0))
        elif address in (0xF2910048, 0xF2910044):
            state["heartbeats"] += 1
            if state["heartbeats"] >= 4:
                uc.emu_stop()

    cpu.hook_add(UC_HOOK_MEM_READ, on_read)
    cpu.hook_add(UC_HOOK_MEM_WRITE, on_write)
    cpu.reg_write(UC_ARM_REG_CPSR, 0xD3)
    cpu.reg_write(UC_ARM_REG_R0, context)
    cpu.reg_write(UC_ARM_REG_SP, stack + 0x2000)
    cpu.reg_write(UC_ARM_REG_LR, stop)
    cpu.emu_start(base + entry, stop, count=2000000)

    result_word = struct.unpack("<I", cpu.mem_read(context + 28, 4))[0]
    r0_ret = cpu.reg_read(UC_ARM_REG_R0)
    return cpu, frame_va, state, result_word, r0_ret


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

    # 1. Senser base (0x22c48000) on primary slot 0x6441b27c with PL310 enabled
    cpu, frame_va, state, result, _ = run_display_case(code, entry, slot_va=0x6441B27C, frame_pa=0x22C48000, cur_dma=0x22C84E80, pl310_ctrl=1)
    assert result == PROBE_OK and state["heartbeats"] >= 4, (hex(result), state)
    assert state["l2_cleans"] == FRAME_BYTES // 32 and state["l2_syncs"] == 1, state
    row0 = struct.unpack("<640H", cpu.mem_read(frame_va, 1280))
    row479 = struct.unpack("<640H", cpu.mem_read(frame_va + 479 * 1280, 1280))
    expected_row = tuple(PALETTE[col // 80] for col in range(640))
    assert row0 == expected_row and row479 == expected_row

    # 2. Live-view base (0x1968f000) on secondary slot 0x644194d8 with PL310 disabled
    _, _, state2, result2, _ = run_display_case(code, entry, slot_va=0x644194D8, frame_pa=0x1968F000, cur_dma=0x19690000, pl310_ctrl=0)
    assert result2 == PROBE_OK and state2["heartbeats"] >= 4 and state2["l2_cleans"] == 0, (hex(result2), state2)

    # 3. Failure guards: bad slot (stage 2), out-of-range cur_dma (stage 2), rearm on recheck (stage 5), bad handoff (stage 1)
    _, _, _, r_bad_slot, ret1 = run_display_case(code, entry, bad_slot=True)
    assert r_bad_slot == 2 and ret1 == 1, (r_bad_slot, ret1)
    _, _, _, r_bad_dma, ret2 = run_display_case(code, entry, frame_pa=0x22C48000, cur_dma=0x1968F000)
    assert r_bad_dma == 2 and ret2 == 1, (r_bad_dma, ret2)
    _, _, _, r_rearm, ret3 = run_display_case(code, entry, rearm_on_recheck=True)
    assert r_rearm == 5 and ret3 == 1, (r_rearm, ret3)
    _, _, _, r_handoff, ret4 = run_display_case(code, entry, mutate_handoff=(0, 0))
    assert r_handoff == 1 and ret4 == 1, (r_handoff, ret4)

    print("Verified packaged full-LCD image, primary/secondary slots, PL310 L2 clean, 640x480 pixels, and 4 failure guards.")


if __name__ == "__main__":
    main()
