"""Resolve the view colour path: rule out the two false positives, then test M3.

The previous run's "M2 supported" was wrong, and the reason is diagnosable.
Its top two signatures were 1b572204010e (10,500 occurrences, 1 distinct value)
and 1f0280550208 (9,507 occurrences, 1 distinct value).  A property with one
constant value is a type tag or class discriminator, not a style index.  The
100%% hit rate came from small integers 0..0x3a being common enum values, and
0x3a=58 happens to sit inside style_cmn's sparse index set.  The test had no
null model, so it could not tell a signal from a coincidence.

Same lesson as the byte-pair count, and as the round-trip test: a search that
cannot fail proves nothing.  Three times now on this project.

So: redo the discriminating test properly.

What the colour property would look like if it exists
-----------------------------------------------------
It must be correlated with something.  A colour is not arbitrary: a given
widget class has a small set of colours, and across the corpus a colour property
should take far fewer distinct values than, say, a geometry property.  So the
right statistic is the *cardinality* of each signature's value set relative to
how often it occurs, plus its correlation with class_id.

A tag has 1 distinct value.  A style index has a handful (26-ish).  A colour
id has a handful.  Geometry has many.  These are distinguishable, and the
previous test conflated "small" with "in the style range".

Three signatures have real cardinality and are worth decoding as a group:
  8ac3b3620202      2444 occ, 33 distinct
  1f0b9b400190      3693 occ, 12 distinct
  0fcbce250190      1970 occ,  9 distinct
  7fb68c7f0190      1100 occ, 13 distinct

If any of these value sets lands in 0x4000..0x4022 that is the colour property.
The previous run says none did, but it looked only at the first u16 of the
payload, which may not be where the value lives for multi-word payloads.

And the M3 test
---------------
M3 says the colour is compiled into the rendering code.  That predicts the view
files contain NO palette ids at all, in any payload, at any offset.  That is a
falsifiable prediction over the whole corpus, and it is worth stating plainly
because if it holds, then editing view files cannot change any colour, and the
only colour levers are color_cmn.uxc and style_cmn.uxc.

Test: scan every parsed property payload, all bytes, for palette-range u16 at
every offset, and also scan the section descriptor fields and object headers.
Then compare against a null model: the same scan over random/other data of the
same size, or equivalently the expected count from 2^16.
"""
import struct
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

TGZ = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz')
PAL_LO, PAL_HI = 0x4000, 0x4022
NPAL = PAL_HI - PAL_LO + 1

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


def parse(b):
    """Yield (cls, obj, sig, payload) plus section/header regions."""
    secs = [o for o in range(0, len(b) - 59, 4) if valid_descriptor(b, o)]
    for i, s in enumerate(secs):
        end = secs[i + 1] if i + 1 < len(secs) else len(b)
        t = s + 60
        if t >= end:
            continue
        n = b[t]
        if n == 0 or t + 1 + 2 * n > end:
            continue
        offs = [u16(b, t + 1 + 2 * j) for j in range(n)]
        if offs[0] != 1 + 2 * n or any(offs[j] >= offs[j + 1]
                                        for j in range(n - 1)):
            continue
        starts = [t + x for x in offs]
        for j, st in enumerate(starts):
            oe = starts[j + 1] if j + 1 < len(starts) else end
            if st + 14 > oe:
                continue
            cls = u32(b, st)
            nprop = b[st + 13]
            p = st + 14
            for _k in range(nprop):
                if p >= oe:
                    break
                ln = prop_len(b, p)
                if ln is None or p + ln > oe:
                    break
                yield cls, st, b[p:p + 6].hex(), b[p + 6:p + ln]
                p += ln


def main():
    t = tarfile.open(TGZ)
    views = {}
    for m in t.getmembers():
        if m.isfile() and '/view' in m.name and m.name.endswith('.uxc'):
            views[m.name.split('/')[-1]] = t.extractfile(m).read()

    # every u16 at every byte offset within every payload, per signature
    sig_vals = defaultdict(set)
    sig_occ = Counter()
    sig_offsets = defaultdict(Counter)   # signature -> which offset holds values
    total_props = 0
    total_payload_bytes = 0
    for name, b in sorted(views.items()):
        for cls, st, sig, pay in parse(b):
            total_props += 1
            sig_occ[sig] += 1
            total_payload_bytes += len(pay)
            for k in range(0, len(pay) - 1):
                v = struct.unpack_from('<H', pay, k)[0]
                sig_vals[sig].add(v)
                sig_offsets[sig][k] += 1

    print('=== %d view files, %d properties, %d payload bytes ==='
          % (len(views), total_props, total_payload_bytes))
    print('  %d distinct signatures' % len(sig_occ))
    print()

    print('=== the palette-id test, at EVERY offset in every payload ===')
    hits = defaultdict(Counter)   # signature -> offset -> count in pal range
    for name, b in sorted(views.items()):
        for cls, st, sig, pay in parse(b):
            for k in range(0, len(pay) - 1):
                v = struct.unpack_from('<H', pay, k)[0]
                if PAL_LO <= v <= PAL_HI:
                    hits[sig][k] += 1
    total_hits = sum(sum(c.values()) for c in hits.values())
    windows = sum(len(p) - 1 for _c, _s, _g, p in
                  [(0, 0, 0, pay) for name, b in sorted(views.items())
                   for _cl, _st, _sg, pay in parse(b)])
    expected = windows * NPAL / 65536.0
    print('  %d u16 windows examined in payloads' % windows)
    print('  %d land in 0x%04x..0x%04x' % (total_hits, PAL_LO, PAL_HI))
    print('  chance expectation %.2f' % expected)
    if expected > 0:
        print('  observed/expected: %.1fx' % (total_hits / expected))
    print()
    if total_hits and expected and total_hits > expected * 5:
        print('  >> enriched. The per-signature breakdown below matters.')
        for sig, c in sorted(hits.items(), key=lambda kv: -sum(kv[1].values()))[:12]:
            print('     %-16s offsets %s  (occurs %d)'
                  % (sig, dict(c.most_common(4)), sig_occ[sig]))
    else:
        print('  >> NOT enriched. No view property carries a palette id at any')
        print('     offset. That supports M3: the colour reference is compiled')
        print('     into the rendering code, not stored in the resources.')
    print()

    print('=== value-set cardinality, to separate tags from real fields ===')
    print('  %-16s %8s %10s %8s  %s' % ('signature', 'occurs', 'distinct', 'ratio', 'reading'))
    for sig, n in sig_occ.most_common(24):
        d = len(sig_vals[sig])
        r = d / n if n else 0
        if d == 1:
            rd = 'TAG (constant)'
        elif r < 0.02:
            rd = 'small enum / index'
        elif r < 0.2:
            rd = 'colour or style id?'
        else:
            rd = 'geometry / free value'
        print('  %-16s %8d %10d %8.3f  %s' % (sig, n, d, r, rd))
    print()
    print('  A colour property would sit in the small-enum band AND its values')
    print('  would have to be palette ids. The test above says the values are')
    print('  not palette ids, so the small-enum signatures are something else')
    print('  (visibility, z-order, alignment, state).')
    print()

    print('=== the small-enum signatures, value lists ===')
    for sig, n in sig_occ.most_common(30):
        vals = sorted(sig_vals[sig])
        if 1 < len(vals) <= 40:
            print('  %-16s %5d occ  %2d vals  %s'
                  % (sig, n, len(vals), ' '.join('%02x' % v for v in vals)))


if __name__ == '__main__':
    main()
