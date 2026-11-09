"""Execute the stock YC metadata builder and alternate VDF send setup offline."""
import argparse
import struct
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('repo', type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.repo / 'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness, MEM, STOP, STACK
from unicorn.arm_const import UC_ARM_REG_R5, UC_ARM_REG_R7, UC_ARM_REG_R8

h = Harness()
source, output = MEM + 0x1000, MEM + 0x2000
h.u.mem_write(source, bytes([0xa5]) * 256)
for slot, expected in enumerate(((3840, 2160, 1), (3840, 2160, 1), (1920, 1080, 1), (1280, 720, 0))):
    for initial in (0, 0xa5):
        h.u.mem_write(output, bytes([initial]) * 60)
        h.run(0x6374ae88, output, source, slot)
        record = bytes(h.u.mem_read(output, 60))
        assert (*struct.unpack_from('<HH', record, 0x18), record[0x2f]) == expected
        assert record[0x36] == initial
    print(f'Metadata slot {slot}: {expected}; depth byte untouched')

h.u.reg_write(UC_ARM_REG_R8, source)
h.u.mem_write(STACK + 0x390, bytes([0xa5]) * 60)
def stop_on_attach(a):
    assert a[1:] == [0, 1, STACK + 0x390]
    assert h.u.mem_read(a[3] + 0x36, 1)[0] == 0
    h.u.emu_stop()
h.callbacks[0x63718110] = stop_on_attach
h.u.reg_write(UC_ARM_REG_R7, 0)
from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_PC
h.u.reg_write(UC_ARM_REG_SP, STACK)
h.u.emu_start(0x6374c8b5, STOP, count=200)
assert h.u.reg_read(UC_ARM_REG_PC) == 0x63718110
print('Alternate 1080p path clears the record, then passes depth byte 0 to the attachment call')

obj, vtable, send = MEM + 0x3000, MEM + 0x4000, MEM + 0x5000
h.put(obj, vtable)
h.put(vtable + 0xb4, send | 1)
for entry, off, pin in ((0x6374c90e, 0x2f8, 3), (0x6374ac4e, 0x2c, 5)):
    h.put(STACK + off, 0xe0b00)
    h.put(STACK + off + 4, 0x263)
    h.u.reg_write(UC_ARM_REG_R5, obj)
    h.u.reg_write(UC_ARM_REG_R8, 0)
    seen = []
    def stop_on_send(a):
        seen.append(a)
        h.u.emu_stop()
    h.callbacks[send] = stop_on_send
    h.u.emu_start(entry | 1, STOP, count=40)
    assert seen == [[obj, pin, 0xe0b00, 0x263]], seen
    print(f'Send at {entry:#x} uses pin {pin}, SDS type and SDS handle')
