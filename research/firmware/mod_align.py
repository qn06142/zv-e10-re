"""Get the instruction alignment right around 0x86e006 before claiming
anything about that second patch site."""
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

VAN = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
DMP = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin').read_bytes()
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)

print('raw vanilla  0x86dff8..0x86e018: %s' % VAN[0x86dff8:0x86e018].hex(' '))
print('raw dumps/   0x86dff8..0x86e018: %s' % DMP[0x86dff8:0x86e018].hex(' '))
print()

# find the enclosing function start by walking back to a push
import struct
start = None
for i in range(0x86e006, 0x86d000, -2):
    hw = struct.unpack_from('<H', VAN, i)[0]
    if (hw & 0xFF00) == 0xB500 and (hw & 0x80):
        start = i
        break
print('enclosing prologue near 0x86e006: 0x%06x' % (start or 0))
print()

for name, buf in (('vanilla', VAN), ('dumps/av-cam.bin', DMP)):
    print('=== aligned disassembly from 0x86dff8 in %s ===' % name)
    base = 0x86dff8
    n = 0
    for ins in md.disasm(buf[base:0x86e020], base):
        flag = ''
        if 0x86e006 <= ins.address < 0x86e010:
            flag = '   <<< inside the 10-byte patched run'
        print('  0x%08x  %-12s %-30s%s' % (ins.address, ins.bytes.hex(' '),
                                           ins.mnemonic + ' ' + ins.op_str, flag))
        n += 1
        if n > 24:
            break
    print()
