"""Decode the ORIL container header: what does av-cam.bin actually load?

Header layout observed:
  0x00  ea00000a  (ARM branch preamble)
  0x04  "ORIL"
  0x08  00000004
  0x0c..0x28  nine words, all 0x635c6xxx  (low 12 bits: 044 058 0b4 068
            078 088 098 09c 0a0)  -> a table clustered in a 0xb4-byte span
  0x30  ARM-mode loader stub (stmdb/bx lr, not Thumb)

Decoding the stub tells us what those words mean, and hence which file
ranges are mapped + executable.  That is the precondition for any cave.
"""
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
av = (BASE / 'dumps' / 'av-cam.bin.bak').read_bytes()
N = len(av)
md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
md.detail = True

print('=== the nine header words ===')
words = []
for off in range(0x0c, 0x2c, 4):
    v = struct.unpack_from('<I', av, off)[0]
    words.append((off, v))
    print('  0x%02x  0x%08x   low12=0x%03x' % (off, v, v & 0xfff))
base = 0x635c6000
print()
print('  relative to 0x%08x:' % base)
for off, v in words:
    print('    0x%02x  +0x%03x' % (off, v - base))
print()

print('=== ARM-mode loader stub at 0x30 ===')
for ins in md.disasm(av[0x30:0x30 + 0x80], 0x30):
    print('  0x%08x  %-10s %s' % (ins.address, ins.bytes.hex(' '),
                                  ins.mnemonic + ' ' + ins.op_str))
print()

print('=== resolve the stub\'s PC-relative literal loads ===')
for off in range(0x30, 0x30 + 0x80, 4):
    ins = next(md.disasm(av[off:off + 4], off, count=1), None)
    if ins is None:
        continue
    ops = ins.operands
    if ins.mnemonic.startswith('ldr') and len(ops) == 2 and ops[1].type != 0:
        from capstone.arm import ARM_OP_MEM
        if ops[1].type == ARM_OP_MEM and ops[1].mem.base == 13:
            la = ((off + 8) & ~3) + ops[1].mem.disp
            if 0 <= la <= N - 4:
                val = struct.unpack_from('<I', av, la)[0]
                print('  @0x%04x %-22s -> pool@0x%04x = 0x%08x' % (
                    off, ins.mnemonic + ' ' + ins.op_str, la, val))
print()

print('=== words at 0xb0..0xe0 (possible size/relocation table) ===')
for off in range(0xb0, 0xe0, 4):
    v = struct.unpack_from('<I', av, off)[0]
    tag = ''
    if 0 < v < N:
        tag = '  <- looks like a file offset (%.2f MB)' % (v / 1e6)
    elif 0x10000000 < v < 0x70000000:
        tag = '  <- looks like a runtime address'
    print('  0x%02x  0x%08x  %10d%s' % (off, v, v, tag))
print()

print('=== content census by region, to locate the segment boundaries ===')
# A segment boundary should show up as a long run of zeros or 0xff,
# or as a change in what the bytes look like.
print('  %-12s %-12s %-12s' % ('offset', 'zero run', '0xff run'))
i = 0
runs = []
while i < N:
    if av[i] == 0:
        j = i
        while j < N and av[j] == 0:
            j += 1
        if j - i >= 0x10000:
            runs.append(('zero', i, j - i))
        i = j
    elif av[i] == 0xff:
        j = i
        while j < N and av[j] == 0xff:
            j += 1
        if j - i >= 0x10000:
            runs.append(('ff', i, j - i))
        i = j
    else:
        i += 1
for kind, off, ln in runs:
    print('  0x%08x  %-12s %d (%.2f MB)  ends 0x%08x' % (
        off, kind, ln, ln / 1e6, off + ln))
print()
print('  content resumes after the last one; the patch site 0xAA15A must be')
print('  inside a mapped+executable run. Any cave must be in the SAME run.')
