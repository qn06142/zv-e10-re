"""Decode DmmConfig.bin's region table and look for the panel surface.

The file is dmm's (display memory manager) module parameter, tagged
"for ilc8g-astra 2020/10/28" -- ilc8g is the panel controller.  The panel's
scanout surface must be one of the regions it manages.

Earlier pass showed a 12-byte-ish repeating record with an address in
~0x0A000000..0xFE000000, a small id, and a size.  Decode it properly this
time (the first attempt crashed before printing) and match region sizes
against plausible framebuffer byte counts.
"""
import struct
from collections import Counter
from pathlib import Path

b = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\DmmConfig.bin').read_bytes()
N = len(b)

# ---- 1. find the record stride empirically -------------------------------
print('=== periodicity: autocorrelation of "is this word nonzero" ===')
nz = [1 if b[i] else 0 for i in range(0, min(N, 0x400), 4)]
best = []
for s in range(3, 41):
    m = sum(nz[i] * nz[i + s] for i in range(len(nz) - s)) / (len(nz) - s)
    best.append((m, s))
best.sort(reverse=True)
for m, s in best[:6]:
    print('  stride %2d words (%3d bytes)  score %.3f' % (s, s * 4, m))
SW = best[0][1]
print('  -> record stride = %d bytes\n' % (SW * 4))

# ---- 2. dump the region table -------------------------------------------
print('=== region table, %d-byte records from 0x50 ===' % (SW * 4))
SZ = SW * 4
regs = []
o = 0x50
while o + SZ <= min(N, 0x260):
    f = struct.unpack_from('<%dI' % SW, b, o)
    regs.append((o, f))
    o += SZ
for o, f in regs:
    print('  0x%04x  %s' % (o, '  '.join('%08x' % x for x in f)))
print()

# ---- 3. extract plausible (base, size) pairs ----------------------------
print('=== plausible (base, size) from each field position ===')
cands = []
for o, f in regs:
    for i, v in enumerate(f):
        if 0x0A000000 <= v < 0x40000000 and (v & 0xFFF) == 0:
            cands.append((o, i, v))
print('  address-like fields: %d' % len(cands))
for o, i, v in cands:
    print('    rec@0x%04x field%d = 0x%08x  (%.1f MB)'
          % (o, i, v, v / 1048576.0))
print()

# ---- 4. match against framebuffer sizes ---------------------------------
print('=== do any region SIZES match a plausible panel framebuffer? ===')
PANELS = []
for w, h in ((640, 480), (480, 640), (320, 240), (800, 480), (960, 540),
             (1024, 600), (1280, 720), (640, 360), (480, 272), (921600, 1)):
    for bpp in (1, 2, 3, 4):
        PANELS.append((w, h, bpp, w * h * bpp))
sizes = set()
for o, f in regs:
    for v in f:
        sizes.add(v)
hit = False
for w, h, bpp, sz in PANELS:
    if sz in sizes:
        print('  MATCH %dx%d x%d = %d bytes present' % (w, h, bpp, sz))
        hit = True
if not hit:
    print('  no exact match; nearest region sizes to common FB byte counts:')
    for w, h, bpp, sz in PANELS[:0]:
        pass
    near = sorted(sizes & set(range(0x10000, 0x4000000)))
    print('  region-size-like values present: %s'
          % [hex(v) for v in near[:24]])

# ---- 5. the ilc8g section: what's around the version banner? ------------
print()
print('=== 0x100-0x240 as bytes, looking for the display block ===')
for o in range(0x100, 0x240, 16):
    print('  0x%04x  %s' % (o, b[o:o + 16].hex(' ')))
