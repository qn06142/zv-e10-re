"""Locate the framebuffer descriptor inside DmmConfig.bin.

Confirmed: the file is the memory map (its addresses match /proc/cmdline
exactly: 0x11000000, 0x15800000, 0x20200000, 0x23E00000) and its trailer
says "for ilc8g-astra 2020/10/28".  ilc8g is the panel controller.

So: find the panel's buffer descriptor -- base address, width, height, pitch
and format.  Strategy:
  1. locate the aperture we already know (0x6AA00000, wbi_cmpr) and dump the
     records around it, since those are the display records
  2. sweep for (size, address) record pairs
  3. look for geometry: a pitch (width*bpp) adjacent to width/height
"""
import re
import struct
from pathlib import Path

b = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\DmmConfig.bin').read_bytes()
N = len(b)

print('=== 1. does the file mention the aperture we already know? ===')
for a in (0x6AA00000, 0x15800000, 0x11000000, 0x20200000, 0x23E00000,
          0x03085000, 0x035A5000, 0x0A916000, 0x635C6000):
    for i in range(0, N - 4, 4):
        if struct.unpack_from('<I', b, i)[0] == a:
            print('  0x%08x at word offset 0x%06x (file 0x%06x)' % (a, i, i))
            break
    else:
        print('  0x%08x  absent' % a)
print()

print('=== 2. first 0x300 as 16-byte records (4 LE words each) ===')
for o in range(0x40, 0x300, 16):
    w = struct.unpack_from('<4I', b, o)
    print('  0x%06x  %08x %08x %08x %08x   | %11d %11d %11d %11d'
          % (o, w[0], w[1], w[2], w[3],
             *[struct.unpack('<i', struct.pack('<I', x))[0] for x in w]))
print()

print('=== 3. sweep for (count/size, address) pairs, address in RAM window ===')
# a record is plausible if one word is a plausible buffer size (<= 8 MB, >=
# 64 KB) and the NEXT word is a plausible base (>= 0x0A000000, aligned 0x1000)
found = []
for o in range(0, N - 8, 4):
    a, c = struct.unpack_from('<II', b, o)
    if 0x10000 <= a <= 0x800000 and c >= 0x0A000000 and (c & 0xFFF) == 0:
        found.append((o, a, c))
    if 0x10000 <= c <= 0x800000 and a >= 0x0A000000 and (a & 0xFFF) == 0:
        found.append((o, c, a))
print('  %d candidate (size, base) pairs' % len(found))
for o, sz, ad in found[:40]:
    print('    @0x%06x  size %8d (0x%06x)  base 0x%08x   %s'
          % (o, sz, sz, ad, ''))
print()

print('=== 4. geometry hunt: pitch = width*bpp adjacent to a width/height pair ===')
# look for 4-byte windows containing (w, h, pitch) with h<w<=4096 and
# pitch in {w, 2w, 3w, 4w} for bpp 8/16/24/32
hits = []
for o in range(0, N - 16, 4):
    q = struct.unpack_from('<4I', b, o)
    for k in range(3):
        w_, h_, p_ = q[k], q[k + 1], q[k + 2]
        if (16 <= w_ <= 4096 and 16 <= h_ <= 4096 and w_ > h_
                and p_ in (w_, 2 * w_, 3 * w_, 4 * w_)):
            hits.append((o, w_, h_, p_))
print('  %d (w,h,pitch) triples' % len(hits))
for o, w_, h_, p_ in hits[:30]:
    print('    @0x%06x  %d x %d  pitch %d  (bpp %d)'
          % (o, w_, h_, p_, p_ * 8 // w_))
print()

print('=== 5. any 2-byte pair that is a plausible panel mode ===')
RES = {240, 272, 288, 320, 360, 400, 480, 512, 640, 720, 768, 800, 960,
       1024, 1280, 1440, 1920}
pairs = {}
for o in range(0, N - 4, 2):
    a, c = struct.unpack_from('<HH', b, o)
    if a in RES and c in RES and a > c:
        pairs.setdefault((a, c), []).append(o)
for (a, c), offs in sorted(pairs.items(), key=lambda kv: -len(kv[1]))[:20]:
    print('    %dx%d  x%d   first @0x%06x' % (a, c, len(offs), offs[0]))
print()

print('=== 6. tail of the file (the ilc8g-astra banner) ===')
print(b[0x130C0:0x13180].hex(' '))
print(repr(b[0x130C0:0x13180].decode('latin1', 'replace')))
