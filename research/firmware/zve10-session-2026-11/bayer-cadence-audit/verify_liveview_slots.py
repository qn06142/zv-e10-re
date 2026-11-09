"""Execute stock LiveView notification and DFE per-slot setup slices."""
import argparse
from pathlib import Path
import struct
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('repo', type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.repo / 'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness, MEM, STOP, STACK
from unicorn.arm_const import UC_ARM_REG_R4, UC_ARM_REG_SP, UC_ARM_REG_PC

h = Harness()
ctx, owner = MEM + 0x10000, MEM + 0x20000
h.put(ctx + 0x85c, 3)
h.put(ctx + 0x9d8, 4)
h.put(ctx + 0x6798, owner)
h.put(ctx + 0x7214, 5)
counter = owner + 0x6fec
events = []


def capture_notification(regs):
    assert regs[0] == 0x12345678
    events.append(struct.unpack('<IH', h.u.mem_read(regs[1], 6)))
    h.ret(0)


h.callbacks[0x637aac18] = lambda _: h.ret(0x12345678)
h.callbacks[0x63d2a730] = capture_notification
for n in range(9):
    h.put(counter, n)
    events.clear()
    expected = {0: [(0, 1)], 6: [(3, 1)]}.get(n, [])
    assert h.run(0x63d8a232, ctx) == bool(expected)
    assert h.word(counter) == n + 1 and events == expected
print('Exposure-wait counter advances on all nine calls; only two emit control notifications')

params = []


def capture_params(regs):
    params.append(tuple(regs[:2]))
    h.ret(0)


h.callbacks.update({0x63d782a4: capture_params, 0x63d785b4: capture_params,
                    0x63d8a154: lambda _: h.u.emu_stop()})
for slot in range(4):
    params.clear()
    h.put(ctx + 0x7208, slot)
    h.put(owner + 0x59c8 + 4 * slot, 0x1000 + slot)
    h.u.reg_write(UC_ARM_REG_R4, ctx)
    h.u.reg_write(UC_ARM_REG_SP, STACK)
    h.u.emu_start(0x6390b991, STOP, count=100)
    assert h.u.reg_read(UC_ARM_REG_PC) == 0x63d8a154
    assert h.word(ctx + 0x6cec) == 0x1000 + slot
    assert params == [(ctx + 0x17d0, owner + 0x67c8 + 0x250 * slot),
                      (ctx + 0x1a20, owner + 0x6c68 + 0x1c0 * slot)]
print('DFE setup uses independent context +0x7208 index in all four fixtures')

# Run the native RAW dump call-site gate through the following mask update.
from unicorn.arm_const import UC_ARM_REG_R6
config, table = MEM + 0x30000, MEM + 0x40000
h.put(table + 0x4b04, config)
h.u.mem_write(ctx + 0x67b2, struct.pack('<H', 0x267))
dumps = []

def capture_dump(a):
    dumps.append((a, h.word(h.u.reg_read(UC_ARM_REG_SP))))
    h.ret(0)

h.callbacks[0x6390897c] = capture_dump
h.callbacks[0x638f8f62] = lambda _: h.u.emu_stop()
for flags, field, mode, expected in (
    (0, 0, 2, False), (0, 0, 3, True), (0, 1, 3, True),
    (0x10, 0, 2, True), (0x10, 1, 2, False),
    (0x20, 1, 2, True), (0x20, 0, 3, False),
):
    dumps.clear()
    h.u.mem_write(config + 0x6a, bytes([flags]))
    h.put(ctx + 0x200, field)
    h.put(ctx + 0x720c, mode)
    h.put(ctx + 0x6c04, 0x400)
    h.u.reg_write(UC_ARM_REG_R4, ctx)
    h.u.reg_write(UC_ARM_REG_R6, table)
    h.u.reg_write(UC_ARM_REG_SP, STACK)
    h.u.emu_start(0x638f8f11, STOP, count=100)
    assert h.u.reg_read(UC_ARM_REG_PC) == 0x638f8f62
    assert dumps == ([([0x6a, 0x267, ctx + 0x210, ctx], 1)] if expected else []), (flags,field,mode,dumps)
    assert h.word(ctx + 0x6c04) == 0x2400
print('Seven native tag-0x6a gate cases passed; dump uses context +0x67b2')



# The second native tag-0x6a call can refer to a different RAW allocation.
h.u.mem_write(ctx + 0x67b0, struct.pack('<H', 0x268))
h.callbacks[0x638f90da] = lambda _: h.u.emu_stop()
for mode, handle in ((2, 0x267), (3, 0x268), (5, 0x267)):
    dumps.clear()
    h.put(ctx + 0x790, mode)
    h.u.reg_write(UC_ARM_REG_R4, ctx)
    h.u.reg_write(UC_ARM_REG_SP, STACK)
    h.u.emu_start(0x638f90b7, STOP, count=100)
    assert h.u.reg_read(UC_ARM_REG_PC) == 0x638f90da
    assert dumps == [([0x6a, handle, ctx + 0x210, ctx], 1)]
print('Second tag-0x6a call selects +0x67b0 in mode 3 and +0x67b2 otherwise')
