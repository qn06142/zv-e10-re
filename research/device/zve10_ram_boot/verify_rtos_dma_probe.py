"""Check exact grouped LED reports and absence of DMA writes in the probe."""
import argparse
import struct
from pathlib import Path

from unicorn import UC_ARCH_ARM, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_MODE_ARM, Uc
from unicorn.arm_const import UC_ARM_REG_CPSR, UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_SP

from build_rtos import HEADER, package_image

TIMER = 0xF240310C
ON, OFF = 0xF2910048, 0xF2910044
XDMAC = 0xF0000030
DMA330 = 0xF0030108
AIF = 0xF3441304
STEP = 700_000


def run_probe(code, flags, invalid=False, stalled=False):
    base, context, stack, arena, stop = 0x100000, 0x2000000, 0x2100000, 0x2200000, 0x2300000
    cpu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    for start, size in (
        (base, 4096), (context, 4096), (stack, 8192), (arena, 16384), (stop, 4096),
        (0xF0000000, 4096), (0xF0010000, 4096), (0xF0030000, 4096),
        (0xF3441000, 4096), (0xF2403000, 4096), (0xF2910000, 4096),
    ):
        cpu.mem_map(start, size)
    if stalled:
        limit = struct.pack("<I", 16_000_000)
        assert code.count(limit) == 1
        code = code.replace(limit, struct.pack("<I", 64))
    cpu.mem_write(base, code)
    cpu.mem_write(context, HEADER.pack(0x4852565A, 1, 32, int(not invalid),
                                       arena, 0x04000000, 16384, 0))
    for reg, value in (
        (UC_ARM_REG_R0, context), (UC_ARM_REG_SP, stack + 8192),
        (UC_ARM_REG_LR, stop), (UC_ARM_REG_CPSR, 0xD3),
    ):
        cpu.reg_write(reg, value)
    if flags & 2:
        cpu.mem_write(DMA330, struct.pack("<I", 1))
    if flags & 4:
        cpu.mem_write(AIF, struct.pack("<I", 1 << 31))

    state = {"tick": 0xFFFFE000, "xdmac_reads": 0}
    led = []

    def timer_read(uc, _access, address, _size, _value, _data):
        if not stalled:
            state["tick"] = (state["tick"] + STEP) & 0xFFFFFFFF
        uc.mem_write(address, struct.pack("<I", state["tick"]))

    def xdmac_read(uc, _access, address, _size, _value, _data):
        state["xdmac_reads"] += 1
        if flags & 1 and state["xdmac_reads"] == 10:
            uc.mem_write(address, struct.pack("<I", 8))

    def write(uc, _access, address, size, value, _data):
        assert size == 4
        if stack <= address < stack + 8192 or arena <= address < arena + 256:
            return
        if address == context + 28:
            return
        assert address in (ON, OFF) and value == 1
        led.append((address, state["tick"]))
        if len(led) == 2 * flags + 1:
            uc.emu_stop()

    cpu.hook_add(UC_HOOK_MEM_READ, timer_read, begin=TIMER, end=TIMER)
    cpu.hook_add(UC_HOOK_MEM_READ, xdmac_read, begin=XDMAC, end=XDMAC)
    cpu.hook_add(UC_HOOK_MEM_WRITE, write)
    cpu.emu_start(base, stop, count=100_000)

    assert struct.unpack("<I", cpu.mem_read(context + 28, 4))[0] == flags
    if flags:
        assert struct.unpack("<3I", cpu.mem_read(arena, 12)) == (flags, flags & 1, flags & 6)
        assert [a for a, tick in led] == [ON, OFF] * flags + [ON]
        assert (led[-1][1] - led[-2][1]) & 0xFFFFFFFF == 16 * STEP
    else:
        assert not led and cpu.reg_read(UC_ARM_REG_R0) == int(invalid or stalled)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    artifact = args.image.read_bytes()
    code = artifact[HEADER.size:]
    assert package_image(code, 0) == artifact
    for flags in range(8):
        run_probe(code, flags)
    run_probe(code, 0, invalid=True)
    run_probe(code, 0, stalled=True)
    print("Verified all eight LED masks, quiet return, invalid ABI and stalled timer.")


if __name__ == "__main__":
    main()
