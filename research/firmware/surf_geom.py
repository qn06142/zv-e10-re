"""Establish the geometry of the panel surface (s4, /dev/stream @ 0x228B2000).

Why s4 is the panel, on evidence rather than assertion:

  s3 (0x3F7ED000)  longest run of one byte value in 16 KB: 3      -> noise
  s4 (0x228B2000)  longest run of one byte value in 16 KB: 1513   -> flat
                                                                    background
                                                                    regions, as
                                                                    a rendered
                                                                    UI has

s3's other statistics fit too: 2.8% zeros, all 256 byte values, mean 81.  That
is the `wbi_cmpr` writeback-compressed surface from /proc/cmdline, i.e. a
transport buffer, not something the panel scans out.

s4 renders as repeated glyph-like blocks in all three pixel-format views and is
89.3% zeros, which is a dark UI (consistent with the panel currently looking
black).

Before writing to it, pin the geometry: the run lengths and the block repeat
distance give the pitch and pixel size.  Getting this right is what makes a
targeted, reversible poke possible instead of a blind 2 MB overwrite.
"""
import struct
from collections import Counter
from pathlib import Path

D = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera')
p = D / 's4.bin'
raw = p.read_bytes()
magic, mmap = struct.unpack_from('<II', raw, 0)
d = raw[8:]
print('=== s4  /dev/stream offset 0x228B2000  mmap -> 0x%08x  %d B ==='
      % (mmap, len(d)))
print()

# ---- run-length structure ------------------------------------------------
print('=== runs of a single repeated byte value (longest 20) ===')
runs = []
i = 0
n = len(d)
while i < n:
    j = i
    while j < n and d[j] == d[i]:
        j += 1
    runs.append((j - i, d[i], i))
    i = j
runs.sort(reverse=True)
for L, v, o in runs[:20]:
    print('   len %6d  value 0x%02x  at 0x%08x' % (L, v, o))
print()

# ---- the dominant value and the period of the structured region ----------
print('=== dominant values ===')
h = Counter(d)
for v, c in h.most_common(8):
    print('   0x%02x  x%-9d %5.2f%%' % (v, c, 100.0 * c / len(d)))
bg = h.most_common(1)[0][0]
print('  -> background value 0x%02x' % bg)
print()

# ---- find the vertical repeat: compare each row to the one N rows up ----
print('=== vertical repeat search (row-to-row difference) ===')
# try candidate widths at 1 and 2 bytes/pixel over the structured region
base = len(d) // 3
win = d[base:base + 0x20000]
cands = []
for w in range(64, 2049):
    for bpp in (1, 2):
        pitch = w * bpp
        if pitch < 64 or pitch > 4096:
            continue
        step = max(1, (len(win) - pitch) // 800)
        tot = c = 0
        for j in range(0, len(win) - pitch, step):
            x = win[j] - win[j + pitch]
            tot += x if x >= 0 else -x
            c += 1
        cands.append((tot / c, pitch, w, bpp))
cands.sort()
for m, pitch, w, bpp in cands[:12]:
    print('   w=%4d bpp=%d  pitch %5d  meandiff %.4f' % (w, bpp, pitch, m))
print()

# ---- how wide are the glyph blocks? measure horizontal run structure -----
print('=== horizontal block structure in one structured line ===')
# find a line with lots of non-background bytes
best = None
for off in range(0, len(win) - 2048, 256):
    line = win[off:off + 2048]
    nz = sum(1 for x in line if x != bg)
    if best is None or nz > best[0]:
        best = (nz, off, line)
nz, off, line = best
print('   most active 2 KB window at +0x%06x: %d non-background bytes' % (off, nz))
print('   %s' % line[:128].hex(' '))
# run lengths of non-background within the line
runs2 = []
i = 0
while i < len(line):
    if line[i] != bg:
        j = i
        while j < len(line) and line[j] != bg:
            j += 1
        runs2.append(j - i)
        i = j
    else:
        i += 1
print('   non-background run lengths: %s' % runs2[:40])
print()

# ---- does the surface change between two dumps? (is it live?) ----------
print('=== is the surface live? compare s4 against itself at two offsets ===')
a = d[:0x1000]
b = d[len(d) // 2:len(d) // 2 + 0x1000]
print('   first 4 KB vs middle 4 KB identical: %s' % (a == b))
