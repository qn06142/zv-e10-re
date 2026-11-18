"""Fault-inject both stock and candidate UVC teardown instructions."""
import io
from itertools import product
from pathlib import Path
import sys

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                               UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5,
                               UC_ARM_REG_R6, UC_ARM_REG_SP, UC_ARM_REG_LR,
                               UC_ARM_REG_PC)
from build import build, ENTRY, END


def run(image, audio, fail_audio, fail_video, fail_close=False):
    elf = ELFFile(io.BytesIO(image))
    u = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    u.mem_map(0, 0x50000)
    for s in elf.iter_segments():
        if s['p_type'] == 'PT_LOAD':
            u.mem_write(s['p_vaddr'], s.data())
    obj, stop, sp = 0x30000, 0x32000, 0x4f000
    u.mem_write(obj + 0xd0, audio.to_bytes(4, 'little', signed=True))
    u.mem_write(obj + 0x8c, (13).to_bytes(4, 'little'))
    u.reg_write(UC_ARM_REG_R0, obj)
    u.reg_write(UC_ARM_REG_SP, sp)
    u.reg_write(UC_ARM_REG_LR, stop | 1)
    for reg in (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6):
        u.reg_write(reg, reg)
    trace = []

    def intercept(cpu, pc, size, _):
        if pc not in (0x8bb0, 0x8e54):
            return
        fd = cpu.reg_read(UC_ARM_REG_R0)
        fd = fd if fd < 2**31 else fd - 2**32
        if pc == 0x8bb0:
            assert cpu.reg_read(UC_ARM_REG_R1) == 0xe001
            trace.append(('unregister', fd))
            rc = -1 if (fail_video if fd == 13 else fail_audio) else 0
        else:
            trace.append(('close', fd))
            rc = -1 if fail_close else 0
        for reg in (UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3):
            cpu.reg_write(reg, 0xdeadbeef)
        cpu.reg_write(UC_ARM_REG_R0, rc & 0xffffffff)
        cpu.reg_write(UC_ARM_REG_PC, cpu.reg_read(UC_ARM_REG_LR))

    u.hook_add(UC_HOOK_CODE, intercept)
    u.emu_start(ENTRY | 1, stop, count=100)
    assert u.reg_read(UC_ARM_REG_PC) == stop
    assert u.reg_read(UC_ARM_REG_SP) == sp
    assert all(u.reg_read(reg) == reg for reg in (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6))
    return trace, u.reg_read(UC_ARM_REG_R0)


stock = Path(sys.argv[1]).read_bytes()
candidate = build(stock)
offset = next(ELFFile(io.BytesIO(stock)).address_offsets(ENTRY, END - ENTRY))
assert len(stock) == len(candidate)
assert stock[:offset] == candidate[:offset] and stock[offset+END-ENTRY:] == candidate[offset+END-ENTRY:]
assert run(stock, 12, True, False) == ([('unregister', 12)], 9)
assert run(stock, 12, False, True) == ([('unregister', 12), ('unregister', 13)], 9)
for audio, fail_audio, fail_video, fail_close in product((12, 0, -1), (False, True), (False, True), (False, True)):
    calls = [('unregister', audio), ('unregister', 13)]
    if audio > 0:
        calls.append(('close', audio))
    assert run(candidate, audio, fail_audio, fail_video, fail_close) == (
        calls, 9 if fail_audio or fail_video or (audio > 0 and fail_close) else 0)
try:
    build(stock[:-1] + bytes([stock[-1] ^ 1]))
except ValueError:
    pass
else:
    raise AssertionError('accepted modified input')
print('24 teardown cases passed, both stock failures reproduced, mismatched stock rejected')
