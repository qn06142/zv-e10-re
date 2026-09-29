"""View files: same record? And which colours does each screen actually use?

style_cmn.uxc is now solved with real evidence rather than a guess:

    stride 36, record start at marker-1, u8 index at +0, RGBA at +12
    +1..+4  constant marker a0 07 26 08
    +5..+11 all zero
    +15 alpha constant ff, +18 =04, +20 =01, +28 =03
    index is sparse: 00..0b, 1f, 23, 24, 27, 31..3a
    17 distinct RGBA quads, alpha always ff

The discriminator that made this trustworthy: the byte at marker-1 counts up by
one across 100% of usable records, while marker-2 through marker-8 all score 0%.
That separates the real boundary from the "the length divides evenly" coincidence
that fooled the previous two attempts.

The palette is warm and clearly designed: dd6600 amber, aa4400 brown, dd8100
orange, aa6300 dark amber, cc8800 gold, over dddddd/aaaaaa/999999/777777 greys
and 2c2c2c near-black.

Now the same treatment for the view files, which is where the interesting
question lies: does each screen carry its own colours?  If the view records have
the same shape, then a screen's appearance is directly editable, and 290 files
become 290 independent levers.  If they differ, the layout is per-file-type and
each needs its own treatment.

Reported per file: whether the marker exists, whether the index field is a
rising counter (the layout test), the distinct colours found, and the bytes that
would be touched.  Files that fail the layout test are reported as failures
rather than being forced into the template -- that discipline is the whole point
after two wrong attempts.
"""
import struct
import tarfile
from collections import Counter
from pathlib import Path

CANDIDATES = [
    Path(r'F:\RE_DUMP\TREES\usr_share.tgz'),
    Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz'),
]
MARKER = bytes([0xa0, 0x07, 0x26, 0x08])
STRIDE = 36
RGBA = 12


def pick():
    for p in CANDIDATES:
        if p.exists():
            try:
                with p.open('rb') as f:
                    f.read(2)
                return p
            except OSError:
                continue
    raise SystemExit('no readable archive')


def load():
    t = tarfile.open(pick())
    out = {}
    for m in t.getmembers():
        if m.isfile() and m.name.endswith('.uxc'):
            out[m.name.split('/')[-1]] = t.extractfile(m).read()
    return out


def find_all(buf, pat):
    out, s = [], 0
    while True:
        i = buf.find(pat, s)
        if i < 0:
            return out
        out.append(i)
        s = i + 1


def layout_ok(b, starts):
    """The index field must count up by one across the run."""
    if len(starts) < 4:
        return None
    vals = [b[s] for s in starts]
    steps = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
    return sum(1 for s in steps if s == 1) / len(steps)


def main():
    d = load()
    print('=== %d uxc files ===' % len(d))
    print()

    with_marker, without = [], []
    for name, b in sorted(d.items()):
        h = find_all(b, MARKER)
        (with_marker if h else without).append((name, b, h))

    print('marker a0 07 26 08 present: %d files' % len(with_marker))
    print('marker absent:               %d files' % len(without))
    print()

    print('=== layout test on files with >=4 records ===')
    print('  %-42s %5s %6s %8s %s'
          % ('file', 'recs', 'step1', 'colours', 'verdict'))
    good, bad, thin = [], [], []
    for name, b, h in with_marker:
        starts = [x - 1 for x in h]
        frac = layout_ok(b, starts)
        cols = set()
        for s in starts:
            o = s + RGBA
            if 0 <= o <= len(b) - 4:
                cols.add(tuple(b[o:o + 4]))
        if frac is None:
            thin.append((name, len(h), len(cols)))
            continue
        row = (frac, len(h), name, len(cols), b, starts, cols)
        (good if frac >= 0.8 else bad).append(row)

    good.sort(key=lambda r: -r[1])
    for frac, n, name, nc, b, starts, cols in good[:30]:
        print('  %-42s %5d %5.0f%% %8d  OK' % (name[:42], n, 100 * frac, nc))
    if len(good) > 30:
        print('  ... and %d more with the same layout' % (len(good) - 30))
    print()
    print('  %d files pass the layout test, %d fail it, %d have too few records'
          % (len(good), len(bad), len(thin)))
    if bad:
        print()
        print('  --- closest failures (step-1 fraction) ---')
        bad.sort(key=lambda r: -r[0])
        for frac, n, name, nc, b, starts, cols in bad[:12]:
            print('  %-42s %5d %5.0f%% %8d' % (name[:42], n, 100 * frac, nc))
    print()

    print('=== colours used, aggregated over files that pass ===')
    agg = Counter()
    for frac, n, name, nc, b, starts, cols in good:
        for s in starts:
            o = s + RGBA
            if 0 <= o <= len(b) - 4:
                agg[tuple(b[o:o + 4])] += 1
    print('  %d distinct quads across %d files' % (len(agg), len(good)))
    for q, c in agg.most_common(30):
        print('    %-14s %5d' % (' '.join('%02x' % x for x in q), c))

    print()
    print('=== a few files with the most distinct colours ===')
    show = sorted(good, key=lambda r: -r[3])[:6]
    for frac, n, name, nc, b, starts, cols in show:
        print()
        print('  %s  (%d recs, %d distinct colours)' % (name, n, nc))
        for s in starts[:14]:
            o = s + RGBA
            v = tuple(b[o:o + 4])
            print('    @0x%06x idx %02x  %s' % (s, b[s], ' '.join('%02x' % x for x in v)))
        if n > 14:
            print('    ... %d more' % (n - 14))

    print()
    print('=== files with NO marker at all ===')
    print('  %d of them; first 40:' % len(without))
    for name, b, _h in without[:40]:
        print('    %-44s %8d B' % (name[:44], len(b)))


if __name__ == '__main__':
    main()
