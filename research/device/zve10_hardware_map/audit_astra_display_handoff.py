"""Verify the stock libObj.so entry points named in Astra's graphics handoff."""
import argparse
import hashlib
import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile
from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_THUMB, Uc
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP

from audit_grm_contracts import LIBOBJ_SHA256

SCRATCH = 0x20000000
STOP = SCRATCH + 0x100
SYSTEM = SCRATCH + 0x200
VTABLE = 0x013bbb78
TERM = 0x006f52ce


def audit(path):
    if hashlib.sha256(path.read_bytes()).hexdigest() != LIBOBJ_SHA256:
        raise ValueError("Unexpected libObj.so identity")
    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        segments = list(elf.iter_segments(type="PT_LOAD"))
        limit = max(s["p_vaddr"] + s["p_memsz"] for s in segments)
        cpu.mem_map(0, (limit + 0xfff) & ~0xfff)
        for segment in segments:
            cpu.mem_write(segment["p_vaddr"], segment.data())
    cpu.mem_map(SCRATCH, 0x4000)
    cpu.mem_write(SYSTEM, struct.pack("<I", VTABLE))
    assert struct.unpack("<I", cpu.mem_read(VTABLE + 12, 4))[0] == TERM | 1

    def run(entry, arg, stubs):
        calls = []

        def intercept(uc, address, _size, _data):
            calls.append((address, uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1)))
            uc.reg_write(UC_ARM_REG_R0, stubs[address])
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

        hooks = [cpu.hook_add(UC_HOOK_CODE, intercept, begin=address, end=address) for address in stubs]
        cpu.reg_write(UC_ARM_REG_SP, SCRATCH + 0x4000)
        cpu.reg_write(UC_ARM_REG_R0, arg)
        cpu.reg_write(UC_ARM_REG_LR, STOP | 1)
        try:
            cpu.emu_start(entry | 1, STOP, count=500)
        finally:
            for hook in hooks:
                cpu.hook_del(hook)
        assert cpu.reg_read(UC_ARM_REG_PC) == STOP
        return calls

    rm_steps = (0x7758e0, 0x775a10, 0x10ed6c)
    assert [c[0] for c in run(0x774110, 0, dict.fromkeys(rm_steps, 1))] == list(rm_steps)
    assert cpu.reg_read(UC_ARM_REG_R0) == 0

    # The real wrapper dispatches through the saved singleton's vtable.
    calls = run(0x6f923c, 0, {0x6f4c10: 0, 0x6f6a9c: SYSTEM, TERM: 0})
    assert calls[0] == (0x6f4c10, 2, 6) and calls[-1] == (0x6f4c10, 2, 7)
    assert [call[0] for call in calls] == [0x6f4c10, 0x6f6a9c, TERM, 0x6f4c10]
    assert calls[2][1] == SYSTEM

    child = SYSTEM + 0x100
    table = child + 0x100
    child_term = table + 0x100
    cpu.mem_write(child, struct.pack("<I", table))
    cpu.mem_write(table + 12, struct.pack("<I", child_term | 1))
    children = (0x6f510c, 0x6f4db0, 0x6f5010, 0x6f4fa0, 0x6f509c, 0x6f51b0)
    stubs = {**dict.fromkeys(children, child), 0x6f4cd4: 0, 0x6f4b7c: 0, child_term: 0,
             0x6fb650: 0, 0x6f5604: 0, 0x6fbf9c: 0}
    for initialized in (0, 1):
        cpu.mem_write(SYSTEM + 0x58, struct.pack("<4I", 1, 0, initialized, 1))
        calls = run(TERM, SYSTEM, stubs)
        expected = [0x6f4cd4]
        if initialized:
            for child_getter in children:
                expected.extend((child_getter, child_term))
                if child_getter == 0x6f4db0:
                    expected.extend((0x6fb650, 0x6f5604))
            expected.append(0x6fbf9c)
        expected.append(0x6f4b7c)
        assert [call[0] for call in calls] == expected
        assert struct.unpack("<4I", cpu.mem_read(SYSTEM + 0x58, 16)) == (1 - initialized, 0, 0, 1 - initialized)
    print("Verified RM exit call order, GRM wrapper dispatch, and both guarded GRM teardown paths.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("libobj", type=Path)
    audit(parser.parse_args().libobj)
