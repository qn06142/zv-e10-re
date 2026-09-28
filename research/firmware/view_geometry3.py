"""The one signature that still looks like geometry: 8ac3b3620202.

view_geometry2.py's fixed-point test came back inconclusive -- scale 100 "won"
at 29/39 clean, which is an artefact of 100 dividing many small numbers, not
evidence.  So the scale question is unresolved and I am not going to pick one by
fiat.

But it also surfaced the real signal in the common-value table:

    0       37875      0x0000
    8       20790      0x0008
    2048     8854      0x0800
    2049     1366      0x0801
    2050      552      0x0802

0x800, 0x801, 0x802 in descending frequency is not geometry.  A coordinate does
not come in bit-11-set triplets.  That is a flag field: bit 11 set means
something, plus a small enum in the low bits.  So the most common values across
all payloads are flags, not coordinates, and the "geometry" candidate from the
previous run (ec18a67a0290, 629 instances, 26 distinct pairs) is more likely a
size or spacing preset than a position -- 26 distinct pairs across 10640 objects
is far too few for per-widget positions.

Which leaves one signature unexamined, and it is the best candidate left by a wide
margin:

    8ac3b3620202    2444 occurrences   1110 distinct u16 values

Highest cardinality in the corpus by a factor of two over anything else.  A
property whose values are almost all different is carrying per-instance data,
not a type tag and not a shared preset.  Its payload is 9 bytes: four u16 and a
trailing byte, which is exactly a rect (x, y, w, h) plus a flag or a fractional
tail byte.

The tests here are the ones that have actually been discriminative:

R1  Four u16 forming a rect: x+w and y+h must stay inside a plausible panel for
    essentially every instance.  A false positive -- four unrelated small ints --
    fails this immediately.
R2  The trailing byte must be constant, or take only a couple of values, if it
    is a flag.  If it is also wide-ranging, the layout is a different shape.
R3  Per-class variance: a rect field varies within a class as widgets move
    around a screen.  A tag does not.
R4  And the null model that this project has learned to require: the same test
    run on a signature that is KNOWN to be a flag must fail.  If the rect test
    passes for 8ac3b3620202 and fails for the flag signatures, the test works.

No writes.  This identifies a field and prints the exact byte offsets that a
layout edit would touch.
"""
import struct
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

TGZ = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz')
TARGET = '8ac3b3620202'
FLAG_SIGS = ['0fcbce250190', '7fb68c7f0190', '1f0b9b400190', '9975ed000190']

KNOWN = {
    '1b572204010e': 16, '1f0280550208': 15, 'c34c39a70111': 7,
    '8ac3b3620202': 15, 'ed06f4340100': 7, 'ec18a67a0290': 11,
    'e0435a90018d': 8, '2146adbf018d': 8, '49760d41018d': 8,
    'dbcf0a6c018d': 8, '0fcbce250190': 8, 'ed188f1a018d': 8,
    '4a311dea018c': 8, '7fb68c7f0190': 8, '82d530c60190': 8,
    '03193943018c': 8, '547e85a6018c': 8, '2dac7cb2018c': 8,
    '571c3df3018c': 8, '94899f21018d': 8, '0d4d93430190': 8,
    'd7520f8d018d': 8, 'ae338fba018d': 8, '3254afad018c': 8,
    '1f0b9b400190': 8,
}
TYPE_LENGTHS = {'018d': 8, '0190': 8, '018c': 8, '0111': 7, '0100': 7,
                '0191': 8, '0208': 15, '0202': 15}


def u16(b, o):
    return struct.unpack_from('<H', b, o)[0]


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def valid_descriptor(b, o):
    if o < 0 or o + 60 > len(b):
        return False
    w = [u32(b, o + 4 * i) for i in range(15)]
    return (w[0] >> 24 == 0x7e and w[1] == 0 and w[2] == 0 and
            w[3] == 2 and w[4] == 0 and w[5] == 9 and
            w[6] == 0 and w[7] == 0x38 and all(x == 0 for x in w[11:15]))


def prop_len(b, p):
    sig = b[p:p + 6].hex()
    if sig in KNOWN:
        return KNOWN[sig]
    return TYPE_LENGTHS.get(b[p + 4:p + 6].hex())


def all_props(b):
    secs = [o for o in range(0, len(b) - 59, 4) if valid_descriptor(b, o)]
    for i, s in enumerate(secs):
        end = secs[i + 1] if i + 1 < len(secs) else len(b)
        t = s + 60
        if t >= end or b[t] == 0 or t + 1 + 2 * b[t] > end:
            continue
        offs = [u16(b, t + 1 + 2 * j) for j in range(b[t])]
        if offs[0] != 1 + 2 * b[t] or any(offs[j] >= offs[j + 1]
                                         for j in range(len(offs) - 1)):
            continue
        starts = [t + x for x in offs]
        for j, st in enumerate(starts):
            oe = starts[j + 1] if j + 1 < len(starts) else end
            if st + 14 > oe:
                continue
            p = st + 14
            for _k in range(b[st + 13]):
                if p >= oe:
                    break
                ln = prop_len(b, p)
                if ln is None or p + ln > oe:
                    break
                yield u32(b, st), b[p:p + 6].hex(), b[p + 6:p + ln], p, st
                p += ln


def rect_test(rows, label):
    """Does this signature look like (x, y, w, h)?  With a panel-width sweep."""
    print('  --- %s (%d instances) ---' % (label, len(rows)))
    if not rows:
        return False
    words = Counter()
    for r in rows:
        pay = r[2]
        n = (len(pay) - 1) // 2
        words[n] += 1
    n = words.most_common(1)[0][0]
    print('     payload words: %s' % dict(words))
    cols = [[] for _ in range(n)]
    tails = Counter()
    for r in rows:
        pay = r[2]
        for k in range(n):
            cols[k].append(struct.unpack_from('<H', pay, k * 2)[0])
        tails[pay[n * 2:].hex() if len(pay) > n * 2 else ''] += 1
    for k in range(n):
        col = sorted(cols[k])
        print('     word %d: min %-6d p25 %-6d p50 %-6d p75 %-6d max %-6d'
              % (k, col[0], col[len(col) // 4], col[len(col) // 2],
                 col[len(col) * 3 // 4], col[-1]))
    print('     trailing bytes: %s' % dict(tails.most_common(4)))
    if n < 4:
        print('     fewer than 4 words -- not a rect')
        return False
    # R1: try each plausible (xi, yi, wi, hi) assignment
    for assume in [(0, 1, 2, 3), (2, 3, 0, 1), (0, 2, 1, 3)]:
        xi, yi, wi, hi = assume
        xs, ys, ws, hs = [], [], [], []
        for r in rows:
            pay = r[2]
            v = struct.unpack_from('<4H', pay, 0)
            xs.append(v[xi] + v[wi])
            ys.append(v[yi] + v[hi])
            ws.append(v[wi])
            hs.append(v[hi])
        bw = max(xs)
        bh = max(ys)
        pos = sum(1 for w in ws if w > 0) / len(ws)
        posh = sum(1 for h in hs if h > 0) / len(hs)
        print('     as (w%d,h%d,w%d,h%d): max x+w=%-6d max y+h=%-6d  w>0 %.0f%%  h>0 %.0f%%'
              % (xi, yi, wi, hi, bw, bh, 100 * pos, 100 * posh))
    return True


def main():
    t = tarfile.open(TGZ)
    views = {}
    for m in t.getmembers():
        if m.isfile() and '/view' in m.name and m.name.endswith('.uxc'):
            views[m.name.split('/')[-1]] = t.extractfile(m).read()

    print('=== 8ac3b3620202: the highest-cardinality signature ===')
    rows = []
    for name, b in sorted(views.items()):
        for cls, sig, pay, off, st in all_props(b):
            if sig == TARGET:
                rows.append((cls, sig, pay, off, st, name))
    print('  %d instances' % len(rows))
    vals = set()
    for _c, _s, pay, _o, _st, _n in rows:
        for k in range(0, len(pay) - 1, 2):
            vals.add(struct.unpack_from('<H', pay, k)[0])
    print('  %d distinct u16 values' % len(vals))
    print()
    rect_test(rows, TARGET)

    print()
    print('=== R4: null model. The same test on KNOWN flag signatures ===')
    for fs in FLAG_SIGS:
        frows = []
        for name, b in sorted(views.items()):
            for cls, sig, pay, off, st in all_props(b):
                if sig == fs:
                    frows.append((cls, sig, pay, off, st))
        if frows:
            rect_test(frows, '%s (known flag)' % fs)

    print()
    print('=== per-class variance for the target ===')
    byc = defaultdict(list)
    for cls, sig, pay, off, st, name in rows:
        byc[cls].append(struct.unpack_from('<4H', pay, 0) + (pay[8:],))
    for cls, vs in sorted(byc.items(), key=lambda kv: -len(kv[1]))[:8]:
        print('  class %08x  %4d instances  %4d distinct quads'
              % (cls, len(vs), len(set(vs))))

    print()
    print('=== sample instances with their file offsets ===')
    for cls, sig, pay, off, st, name in rows[:10]:
        v = struct.unpack_from('<4H', pay, 0)
        print('  %-38s obj 0x%05x prop 0x%05x  %s  tail %s'
              % (name[:38], st, off, ' '.join('%5d' % x for x in v), pay[8:].hex()))

    print()
    print('=== files containing the most instances (edit candidates) ===')
    fc = Counter(r[5] for r in rows)
    for name, n in fc.most_common(12):
        print('  %-42s %4d' % (name[:42], n))


if __name__ == '__main__':
    main()
