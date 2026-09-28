"""The geometry values are fixed-point, not pixels.  Find the real coordinates.

view_geometry.py surfaced the anomaly that matters: the u16 value distribution
across 120,750 payload values is

    p25 = 0      p50 = 8      p75 = 2048    p90 = 17408   p99 = 57344

Those are not pixel coordinates.  2048, 17408 and 57344 are round numbers in
binary -- 0x0800, 0x4400, 0xE000 -- and p75 landing exactly on 0x0800 is the
giveaway.  Pixels do not cluster on powers of two.  Fractions do.

Sony's UI is resolution-independent: the same resources drive the panel and
HDMI output at different sizes, so positions are stored as a fraction of a
reference dimension rather than as absolute pixels.  That would explain all of
it, and it has a testable consequence: if the values are 16.16 or 12.20 fixed
point fractions, then dividing by 2^16 should produce a small set of clean
ratios.

The candidate signature found last run, ec18a67a0290, has 629 instances whose
second word takes {400, 656, 1424, 3216} -- those are not pixels, but
400/65536 = 0.0061 and 3216/65536 = 0.049, which are absurdly small for a
layout fraction.  So a straight 16.16 reading of the whole word is wrong, and
the alternative is a fixed-point scale other than 2^16, or a mixed field.

So: test several fixed-point scales against the observed values and pick the one
that makes the numbers clean.  A scale is correct if dividing by it lands
values on a small set of simple ratios.  That is a real test with a null model,
unlike assuming 2^16.

Scales to test: 2^8, 2^10, 2^12, 2^14, 2^16, and 1024 (a common 10.10 form),
plus the "value is already a 10.6 fraction of 65536" family.

The second test is independent of the scale question and more useful: whatever
the encoding, geometry must correlate with widget class, and a rect must have
its extent fields smaller than its position fields.  Looking for (small, large)
pairings inside single payloads identifies which word is a size and which is a
position regardless of units.
"""
import struct
import tarfile
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

TGZ = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz')

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
                yield u32(b, st), b[p:p + 6].hex(), b[p + 6:p + ln], p
                p += ln


def main():
    t = tarfile.open(TGZ)
    views = {}
    for m in t.getmembers():
        if m.isfile() and '/view' in m.name and m.name.endswith('.uxc'):
            views[m.name.split('/')[-1]] = t.extractfile(m).read()

    vals = []
    for name, b in sorted(views.items()):
        for _c, _s, pay, _o in all_props(b):
            for k in range(0, len(pay) - 1, 2):
                vals.append(struct.unpack_from('<H', pay, k)[0])
    c = Counter(vals)
    print('=== most common u16 values across all payloads ===')
    print('  %d distinct values, %d total' % (len(c), len(vals)))
    print()
    print('  %-8s %8s %s' % ('value', 'count', 'hex'))
    for v, n in c.most_common(30):
        print('  %-8d %8d 0x%04x' % (v, n, v))
    print()

    print('=== fixed-point scale test ===')
    print('  For each candidate scale, how many of the top values become a')
    print('  simple ratio?  A correct scale makes layout numbers clean.')
    print()
    scales = [256, 512, 1024, 2048, 4096, 16384, 32768, 65536, 100, 1000]
    for s in scales:
        clean = 0
        shown = []
        for v, _n in c.most_common(40):
            if v == 0:
                continue
            fr = Fraction(v, s)
            # a simple layout fraction: denominator <= 64 after reduction
            if fr.denominator <= 64:
                clean += 1
                if len(shown) < 8:
                    shown.append('%d=%s' % (v, fr))
        print('  scale %-6d %2d/39 clean   %s' % (s, clean, ', '.join(shown)))
    print()

    print('=== the ec18a67a0290 signature, all instances ===')
    print('  (the only candidate from the previous run; 629 occurrences)')
    rows = []
    for name, b in sorted(views.items()):
        for cls, sig, pay, off in all_props(b):
            if sig == 'ec18a67a0290':
                w = struct.unpack_from('<H', pay, 0)[0]
                h = struct.unpack_from('<H', pay, 2)[0]
                rest = pay[4:].hex()
                rows.append((name, cls, off, w, h, rest))
    print('  %d instances' % len(rows))
    pairs = Counter((w, h) for _n, _c, _o, w, h, _r in rows)
    print()
    print('  distinct (word0, word1) pairs: %d' % len(pairs))
    for (w, h), n in pairs.most_common(30):
        print('    w=%-6d h=%-6d  x%d' % (w, h, n))
    print()
    print('  fraction readings (assume 16.16):')
    for (w, h), n in pairs.most_common(12):
        print('    %d/%d  ->  %.4f , %.4f' % (w, 65536, w / 65536, h / 65536))
    print()
    print('  distinct trailing bytes after the two u16s:')
    tb = Counter(r[5] for r in rows)
    for t, n in tb.most_common(10):
        print('    %-12s x%d' % (t, n))
    print()
    print('=== per-class value sets, is this position or size? ===')
    byc = defaultdict(Counter)
    for _n, cls, _o, w, h, _r in rows:
        byc[cls][(w, h)] += 1
    for cls, cc in sorted(byc.items(), key=lambda kv: -sum(kv[1].values()))[:10]:
        print('  class %08x  %d instances, %d distinct pairs' % (cls, sum(cc.values()), len(cc)))
        for (w, h), n in cc.most_common(5):
            print('      %-6d %-6d x%d' % (w, h, n))
    print()
    print('  If a class shows many distinct pairs, the field varies with')
    print('  position in the layout, so it is geometry.  If each class shows')
    print('  one pair, it is a constant property like a size preset.')


if __name__ == '__main__':
    main()
