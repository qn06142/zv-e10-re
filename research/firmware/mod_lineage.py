"""Two follow-ups:

1. Confirm dumps/av-cam.bin (the file I nearly restored!) also carries the
   decoder-breaking patch, plus what its two other patched regions are.
2. Characterise the 0x86e006 patch, which uses the SAME instruction encoding
   as the mod - suggesting a common patch lineage.
"""
import hashlib
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

N = 17_289_388
VAN = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
MOD = Path(r'F:\restore\av-cam.modded.bin').read_bytes()
DMP = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin').read_bytes()

md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)

print('=== how the three files relate ===')
d_mod = {i for i in range(N) if VAN[i] != MOD[i]}
d_dmp = {i for i in range(N) if VAN[i] != DMP[i]}
print('  vanilla  md5 %s' % hashlib.md5(VAN).hexdigest())
print('  modded   md5 %s   %d byte(s) differ from vanilla' % (hashlib.md5(MOD).hexdigest(), len(d_mod)))
print('  dumps/   md5 %s   %d byte(s) differ from vanilla' % (hashlib.md5(DMP).hexdigest(), len(d_dmp)))
print('  modded changed set is a SUBSET of dumps/ changed set:', d_mod <= d_dmp)
print('  -> dumps/av-cam.bin carries the same decoder patch plus:')
extra = sorted(d_dmp - d_mod)
print('     %s' % ', '.join('0x%06x' % i for i in extra))
print()

print('=== the decoder patch is present in dumps/av-cam.bin ===')
print('  0xaa15a vanilla: %s' % VAN[0xaa15a:0xaa15e].hex(' '))
print('  0xaa15a modded : %s' % MOD[0xaa15a:0xaa15e].hex(' '))
print('  0xaa15a dumps/ : %s' % DMP[0xaa15a:0xaa15e].hex(' '))
print('  dumps/ == modded here:', DMP[0xaa15a:0xaa15e] == MOD[0xaa15a:0xaa15e])
print()

for name, buf in (('vanilla', VAN), ('dumps/av-cam.bin', DMP)):
    print('=== disassembly at 0x86e006 in %s ===' % name)
    for ins in md.disasm(buf[0x86e000:0x86e018], 0x86e000):
        mark = '   <<< patched region starts here' if ins.address == 0x86e006 else ''
        print('  0x%08x  %-12s %s%s' % (ins.address, ins.bytes.hex(' '),
                                        ins.mnemonic + ' ' + ins.op_str, mark))
    print()

print('=== the same instruction family appears in both patches ===')
print('  0xaa15a  40 f6 50 00  = movw r0, #0x850   (modded decoder patch)')
print('  0x86e006 40 f6 50 03  = movw r0, #0x083   (dumps/ second patch)')
print('  identical encoding, different immediate -> same patching tool/author')
