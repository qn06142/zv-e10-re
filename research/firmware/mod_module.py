"""Confirm the mod sits inside the video decoder, and find who calls it."""
import re
import struct
from pathlib import Path

N = 17_289_388
a = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
FUNC = 0x000aa14c
PATCH = 0x000aa15a

print('=== every source filename in the binary, grouped by directory ===')
files = {}
for m in re.finditer(rb'[\x20-\x7e]{6,120}', a):
    s = m.group().decode('ascii')
    if re.fullmatch(r'[\w./+-]+\.(?:cpp|c|h|hpp|cc)', s):
        d = s.rsplit('/', 1)[0] if '/' in s else '(root)'
        files.setdefault(d, []).append((m.start(), s.rsplit('/', 1)[-1]))
for d in sorted(files):
    names = files[d]
    print('  %-14s %3d file(s)   e.g. %s' % (d, len(names), ', '.join(n for _, n in names[:4])))
print()

print('=== the dec/ module in full - is sfmc_dec_input_i.cpp among them? ===')
dec = sorted(files.get('dec', []))
for off, n in dec:
    mark = '   <<<< THE PATCHED FUNCTION IS IN HERE' if abs(off - PATCH) < 0x60000 else ''
    print('  0x%08x  %s%s' % (off, n, mark))
print()

print('=== other sfmc_ symbols/strings anywhere ===')
sf = set()
for m in re.finditer(rb'[\x20-\x7e]{4,80}', a):
    s = m.group().decode('ascii')
    if 'sfmc' in s.lower() or 'SFMC' in s:
        sf.add((m.start(), s))
for off, s in sorted(sf)[:40]:
    print('  0x%08x  %s' % (off, s))
print('  (%d total)' % len(sf))
print()

print('=== direct BL callers of the patched function 0x%06x ===' % FUNC)
callers = []
for i in range(0, N - 4, 2):
    hw1, hw2 = struct.unpack_from('<HH', a, i)
    if hw1 & 0xF800 != 0xF000:
        continue
    if hw1 & 0x0800:
        continue
    s = (hw1 >> 10) & 1
    imm10 = hw1 & 0x3FF
    j1 = (hw2 >> 13) & 1
    j2 = (hw2 >> 11) & 1
    imm11 = hw2 & 0x7FF
    i1 = (~(j1 ^ s)) & 1
    i2 = (~(j2 ^ s)) & 1
    v = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
    if v & 0x1000000:
        v -= 0x2000000
    if i + 4 + v == FUNC:
        callers.append(i)
print('  %d direct call site(s)' % len(callers))
for c in callers:
    print('    0x%08x   (patched fn is %+#07x away)' % (c, FUNC - c))
print()

print('=== the removed callee 0xa9f90 - which source file logs from it? ===')
# scan forward from 0xa9f90 for a pc-relative string load pattern; instead just
# look for a filename string within 0x600 after it
for m in re.finditer(rb'[\x20-\x7e]{6,120}', a[0xa9f90:0xa9f90 + 0x600]):
    s = m.group().decode('ascii')
    if re.fullmatch(r'[\w./+-]+\.(?:cpp|c|h|hpp|cc)', s):
        print('  0x%08x  %s' % (0xa9f90 + m.start(), s))
print()
print('  raw 0xa9f90..0xa9fa0: %s' % a[0xa9f90:0xa9fa0].hex(' '))
print('  (2d e9 f0 47 = PUSH.W with many regs; ca b0 = SUB sp -> a large function)')
