"""Verify which native DFE dispatch cases forward the RAW descriptor pointer."""
import argparse
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('repo', type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.repo / 'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness, MEM, STACK, STOP
from unicorn.arm_const import UC_ARM_REG_R4, UC_ARM_REG_R6, UC_ARM_REG_SP

h = Harness()
ctx = MEM + 0x10000
h.put(ctx + 0x6ce8, 0x3210)
h.put(STACK + 0x40, 0x55)
descriptor = ctx + 0x210
h.put(STACK + 0x8c, descriptor)
h.put(STACK + 0x90, 0x12345678)
routes = {1: (0x63771c30, None), 2: (0x63771bcc, None),
          3: (0x63771b7c, 2), 4: (0x63771a08, 1),
          11: (0x63771b10, 2), 12: (0x63771ac0, 2),
          13: (0x63771a54, 2)}
seen = []

def callback(target, regs):
    seen.append((target, regs))
    h.u.emu_stop()

for target, _ in routes.values():
    h.callbacks[target] = lambda regs, target=target: callback(target, regs)

for case, (target, descriptor_register) in routes.items():
    seen.clear()
    h.u.reg_write(UC_ARM_REG_R4, ctx)
    h.u.reg_write(UC_ARM_REG_R6, case)
    h.u.reg_write(UC_ARM_REG_SP, STACK)
    h.u.emu_start(0x63907d55, STOP, count=100)
    assert len(seen) == 1 and seen[0][0] == target
    regs = seen[0][1]
    if descriptor_register is not None:
        assert regs[descriptor_register] == descriptor
    else:
        assert descriptor not in regs
    print(f'DFE dispatch case {case} -> {target:#x}, descriptor register {descriptor_register}')


# The actual DMM handle takes a separate route from the RAW descriptor.
import struct
from unicorn.arm_const import UC_ARM_REG_PC
request = MEM + 0x30000
address_slot = MEM + 0x40000
h.put(request + 8, address_slot)
h.put(address_slot, 0x30000000)
h.u.mem_write(request + 0xc, struct.pack('<H', 0x267))
h.put(request + 0x10, descriptor)
h.u.mem_write(ctx + 0x214, struct.pack('<H', 0x123))
h.u.mem_write(ctx + 0x218, struct.pack('<H', 0x456))
h.put(ctx + 0x6844, 2)
seen.clear()
h.callbacks[0x637b65d8] = lambda regs: callback(0x637b65d8, regs)
h.u.reg_write(UC_ARM_REG_R4, ctx)
h.u.reg_write(UC_ARM_REG_R6, request)
h.u.emu_start(0x638f5fd9, STOP, count=30)
assert h.u.reg_read(UC_ARM_REG_PC) == 0x637b65d8
assert seen == [(0x637b65d8, [0x30000000, 0x267, 0x456, 0x123])]
print('Separate mode-2 setup forwards the physical address, DMM handle, and two descriptor fields')

# ZIT detection maps the candidate address as an analysis input and associates its handle.
from unicorn.arm_const import UC_ARM_REG_R5
input_record, params = MEM + 0x50000, MEM + 0x51000
h.put(input_record + 4, 0x30000000)
h.u.mem_write(input_record + 8, struct.pack('<H', 0x267))
seen.clear()

def map_input(regs):
    seen.append(('map', regs[:3]))
    h.ret(0x40200000)

def associate_input(regs):
    seen.append(('associate', regs[:2]))
    h.ret(0)

h.callbacks[0x63c48e0c] = map_input
h.callbacks[0x637a8d6c] = associate_input
h.callbacks[0x637a9f5c] = lambda _: h.u.emu_stop()
h.u.reg_write(UC_ARM_REG_R4, params)
h.u.reg_write(UC_ARM_REG_R6, input_record)
h.u.reg_write(UC_ARM_REG_R5, 0)
h.u.reg_write(UC_ARM_REG_SP, STACK)
h.u.emu_start(0x637a9f49, STOP, count=30)
assert h.u.reg_read(UC_ARM_REG_PC) == 0x637a9f5c
assert seen == [('map', [0x30000000, 0x10, 1]), ('associate', [STACK + 0xc, 0x267])]
assert h.word(params) == 0x40200000
print('ZIT detector maps the candidate RAW address and uses the associated DMM handle')
