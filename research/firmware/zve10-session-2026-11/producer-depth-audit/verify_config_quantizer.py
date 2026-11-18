"""Verify the stock configuration quantizer and its copy into the consumer."""
import argparse
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('repo', type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.repo / 'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness, STOP
from unicorn.arm_const import UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R8

h = Harness()
work = h.run(0x6385087c)
published = h.run(0x63850870)
assert (work, published) == (0x6437ffac, 0x643804f0)
assert h.run(0x63850b50) == h.u.mem_read(published + 0xf9, 1)[0]
h.callbacks[0x6385a73c] = lambda _: h.u.emu_stop()
for source in (0, 256, 0x400, 0x1200, 0x3b00, 0x8000):
    h.u.reg_write(UC_ARM_REG_R4, work)
    h.u.reg_write(UC_ARM_REG_R8, source)
    h.u.emu_start(0x6385a70b, STOP, count=50)
    expected = min((source + 256) >> 9, 31)
    assert h.u.mem_read(work + 0xf9, 1)[0] == expected
    h.run(0x63850854)
    assert h.run(0x63850b50) == expected
    print(f'Source {source:#06x} publishes +0xf9 = {expected}')

del h.callbacks[0x6385a73c]
destination = 0x6427803c
h.u.reg_write(UC_ARM_REG_R5, destination)
h.callbacks[0x637d159a] = lambda _: h.u.emu_stop()
h.u.emu_start(0x637d1593, STOP, count=20)
assert h.u.mem_read(destination + 0x36, 1)[0] == 31
print('Original consumer forwards 31 into configuration +0x36 before its later gates')
