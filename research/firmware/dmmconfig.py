"""Analyse /setting/DmmConfig.bin - the dmm (display memory manager) config.

dmm is a 3.1 MB kernel module with users liro (the RTOS) and upm.  Its module
parameter is this file, so it defines how display memory is carved up.  The
goal is the framebuffer: geometry, stride, and the base address of the pool,
which would give us a CPU-visible, writable display surface.

78120 bytes.  Mix of text and binary records, so look at both: printable
strings, and 32-bit words that look like addresses or dimensions.
"""
import re
import struct
import sys
from collections import Counter
from pathlib import Path

P = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\DmmConfig.bin')
b = P.read_bytes()
N = len(b)
print('=== %d bytes ===' % N)
print('  first 64: %s' % b[:64].hex(' '))
print()

print('=== printable strings (>=4 chars) ===')
strs = [(m.start(), m.group().decode('latin1')) for m in re.finditer(rb'[\x20-\x7e]{4,}', b)]
print('  %d strings' % len(strs))
for o, s in strs[:120]:
    print('  0x%06x  %s' % (o, s[:100]))
print()

print('=== record structure guess: aligned 32-bit words, look for repeats ===')
w = [struct.unpack_from('<I', b, i)[0] for i in range(0, N - 4, 4)]
c = Counter(w)
print('  %d words, %d distinct; most common:' % (len(w), len(c)))
for v, n in c.most_common(14):
    print('    0x%08x  x%-6d %10d' % (v, n, struct.unpack('<i', struct.pack('<I', v))[0]))
print()

print('=== words that look like RAM addresses (0x00000000..0x40000000, aligned) ===')
addrs = [(i * 4, v) for i, v in enumerate(w)
         if 0x1000 <= v < 0x40000000 and (v & 0xF) == 0]
print('  %d candidate addresses' % len(addrs))
seen = set()
for o, v in addrs:
    if v in seen:
        continue
    seen.add(v)
    print('    word@0x%06x -> 0x%08x  (%d MB)' % (o, v, v >> 20))
    if len(seen) > 40:
        print('    ...')
        break
print()

print('=== words that look like dimensions (16..8192, common pairs) ===')
dims = [(i * 4, v) for i, v in enumerate(w) if 16 <= v <= 8192]
print('  %d candidates' % len(dims))
for o, v in dims[:40]:
    print('    word@0x%06x -> %d (0x%x)' % (o, v, v))
print()

print('=== big-endian 32-bit words (config may be BE) ===')
wb = [struct.unpack_from('>I', b, i)[0] for i in range(0, N - 4, 4)]
cb = Counter(wb)
print('  %d distinct; most common:' % len(cb))
for v, n in cb.most_common(10):
    print('    0x%08x  x%-6d' % (v, n))
print()

print('=== plausible panel resolutions anywhere in the file ===')
RES = [320, 240, 480, 640, 800, 480, 272, 128, 160, 96, 1280, 720, 1024, 768,
       1920, 1080, 512, 288, 60, 50, 30, 24, 16, 8, 4, 2, 1, 25, 20, 100, 200,
       400, 120, 360, 288, 144, 75, 93, 112]
hits = Counter()
for i in range(0, N - 8, 2):
    a, c2 = struct.unpack_from('<HH', b, i)
    if a in RES and c2 in RES and a >= c2 and a <= 4096 and c2 <= 4096:
        hits[(a, c2, i)] += 1
for (a, c2, o), n in sorted(hits.items(), key=lambda kv: -kv[1])[:25]:
    print('    @0x%06x  %dx%d   (x%d)' % (o, a, c2, n))
