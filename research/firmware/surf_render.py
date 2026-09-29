"""Render a dumped surface as ASCII to see what it actually contains.

s3 (0x3F7ED000) has only 2.8% zeros, all 256 byte values and mean 81 -- it
looks like the compressed panel surface (the `wbi_cmpr` writeback compressor
from /proc/cmdline).  If so it is NOT a raster we can read as pixels, but that
does not matter: the panel is fed from it, so overwriting it makes the panel
display whatever we write.  That is the visible effect, and it needs no
decoding.

This renders s3 at several assumed pixel formats to see whether any of them
produces coherent structure (a raster) or noise (compressed).
"""
import struct
from pathlib import Path

D = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera')
RAMP = ' .:-=+*#%@'


def show(title, rows, cols, get):
    print('  %s  (%dx%d sampled)' % (title, cols, rows))
    for r in range(rows):
        line = []
        for c in range(cols):
            v = get(r, c)
            line.append(RAMP[min(9, (v * 10) // 256)])
        print('   |%s|' % ''.join(line))
    print()


for name in ('s3', 's4'):
    p = D / (name + '.bin')
    if not p.exists():
        continue
    raw = p.read_bytes()
    d = raw[8:]
    print('=== %s  (%d B) ===' % (name, len(d)))
    # sample a window from the middle, where live data is most likely
    off = len(d) // 3
    win = d[off:off + 0x4000]
    ROWS, COLS = 24, 72

    for fmt, bpp in (('1 byte/px', 1), ('2 byte/px (low)', 2), ('2 byte/px (hi)', 2)):
        pitch = COLS * bpp
        rows = min(ROWS, len(win) // pitch)
        if rows < 4:
            continue
        if bpp == 1:
            get = lambda r, c, p_=pitch: win[r * p_ + c]
        elif fmt.endswith('(low)'):
            get = lambda r, c, p_=pitch: win[r * p_ + c * 2]
        else:
            get = lambda r, c, p_=pitch: win[r * p_ + c * 2 + 1]
        show(fmt, rows, COLS, get)

    # is there any long run of identical bytes?  A raster of a flat UI region
    # has them; noise does not.
    best = cur = 1
    for i in range(1, len(win)):
        cur = cur + 1 if win[i] == win[i - 1] else 1
        if cur > best:
            best = cur
    print('  longest run of one byte value in a 16 KB window: %d' % best)
    print()
