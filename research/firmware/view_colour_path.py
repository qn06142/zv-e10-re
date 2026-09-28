"""The view format is solved. Now find the colour path, which is still open.

Verified independently in verify_view_parser.py:
    214/214 view files carry 0x7e section descriptors, 1240 sections, 0 misses
    1240/1240 object index tables satisfy offset[0] == 1 + 2N, 0 failures
    10640 objects indexed, max N = 83

Object boundaries are now derived, not searched.  That is what the marker-gap
approach could never do.

The colour path, though, remains unproven, and it is the thing that actually
matters for editing.  The hardware result is solid -- guides follow palette entry
0x400c -- but the route from a view object to a palette slot has never been
shown.  Three candidate mechanisms:

M1  A property whose value is a palette id.  Searchable: look for a u16
    property payload equal to 0x4000..0x4022 across all 10640 objects, and see
    whether any signature carries them systematically.  If one signature's
    payload is a palette id in many objects, that is the colour property.

M2  A style reference.  style_cmn.uxc has 26 styles indexed 0x00..0x3a
    (sparse).  If a view property references a style index, and the style
    carries a colour, the chain is view -> style -> colour.  Searchable the
    same way: which signature's payloads fall in the style index range and
    vary per object?

M3  A compiled-in default.  The rendering code holds a palette id and the views
    never mention colour at all.  Not searchable from the resource files; needs
    the engine binary, which is on the SD card.

M1 and M2 are both decidable from the parsed corpus.  The discriminator is
distribution: a colour property should be *correlated* with widget class and
should take a small number of distinct palette values, whereas a geometry
property takes many distinct values.  So for every property signature, report
how many distinct payload values it takes and how many fall in the palette id
range.  A signature that is nearly always a palette id is the colour property.

That is the right search, and it is cheap.  It also avoids the mistake that has
now bitten this project three times: counting byte patterns without structural
context.
"""
import json
import struct
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

TGZ = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz')
PAL_LO, PAL_HI = 0x4000, 0x4022
# style_cmn.uxc index values, solved this session
STYLE_IDX = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09,
             0x0a, 0x0b, 0x1f, 0x23, 0x24, 0x27, 0x31, 0x32, 0x33, 0x34,
             0x35, 0x36, 0x37, 0x38, 0x39, 0x3a}
STYLE_COLOUR = {
    0x00: 'dddddd', 0x01: 'dd6600', 0x02: '777777', 0x03: 'dddd00',
    0x04: 'dd0000', 0x05: 'aaaaaa', 0x06: 'aa4400', 0x07: '777777',
    0x08: 'aaaa00', 0x09: 'aa0000', 0x0a: 'dddddd', 0x0b: '000000',
    0x1f: '118800', 0x23: '777777', 0x24: 'bbbbbb', 0x27: 'dddddd',
    0x31: '999999', 0x32: '2c2c2c', 0x33: '999999', 0x34: 'cc8800',
    0x35: 'cc8800', 0x36: '777777', 0x37: '000000', 0x38: '000000',
    0x39: 'dd8100', 0x3a: 'aa6300',
}

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


def walk(b):
    """Yield (class_id, prop_offset, signature, payload_bytes) for every
    property the known signatures can resolve."""
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
                yield cls, p, b[p:p + 6].hex(), b[p + 6:p + ln]
                p += ln


def main():
    t = tarfile.open(TGZ)
    views = {}
    for m in t.getmembers():
        if m.isfile() and '/view' in m.name and m.name.endswith('.uxc'):
            views[m.name.split('/')[-1]] = t.extractfile(m).read()
    print('=== %d view files ===' % len(views))

    sig_all = Counter()          # signature -> occurrences
    sig_pal = Counter()          # signature -> palette-id payloads
    sig_sty = Counter()          # signature -> style-index payloads
    sig_vals = defaultdict(set)  # signature -> distinct u16 first-word values
    total = 0
    for name, b in sorted(views.items()):
        for cls, off, sig, pay in walk(b):
            total += 1
            sig_all[sig] += 1
            if len(pay) >= 2:
                v = struct.unpack_from('<H', pay, 0)[0]
                sig_vals[sig].add(v)
                if PAL_LO <= v <= PAL_HI:
                    sig_pal[sig] += 1
                if v in STYLE_IDX:
                    sig_sty[sig] += 1
    print('  %d property records walked' % total)
    print('  %d distinct signatures' % len(sig_all))
    print()

    print('=== signatures whose u16 payload lands in the palette id range ===')
    print('  %-16s %8s %8s %7s %8s  %s'
          % ('signature', 'occurs', 'as palid', 'pct', 'distinct', 'verdict'))
    rows = []
    for sig, n in sig_all.items():
        p = sig_pal[sig]
        if p:
            rows.append((p / n, p, n, sig))
    rows.sort(reverse=True)
    for pct, p, n, sig in rows[:20]:
        verdict = 'CANDIDATE' if pct > 0.5 and n >= 20 else ''
        print('  %-16s %8d %8d %6.0f%% %8d  %s'
              % (sig, n, p, 100 * pct, len(sig_vals[sig]), verdict))
    if not rows:
        print('  (none)')
    print()
    print('  A signature that is almost always a palette id would be the')
    print('  colour property (M1). A low percentage means the range is hit')
    print('  incidentally and no property carries a colour id directly.')
    print()

    print('=== signatures whose u16 payload lands in the style index range ===')
    print('  %-16s %8s %8s %7s %s' % ('signature', 'occurs', 'as styid', 'pct', 'distinct'))
    rows = []
    for sig, n in sig_all.items():
        s = sig_sty[sig]
        if s:
            rows.append((s / n, s, n, sig))
    rows.sort(reverse=True)
    for pct, s, n, sig in rows[:15]:
        print('  %-16s %8d %8d %6.0f%% %d'
              % (sig, n, s, 100 * pct, len(sig_vals[sig])))
    if not rows:
        print('  (none)')
    print()
    print('  A high percentage here would support the chain')
    print('  view -> style_cmn index -> colour (M2).')
    print()

    print('=== the highest-signal signatures overall ===')
    print('  %-16s %8s %8s %10s %10s'
          % ('signature', 'occurs', 'objects', 'distinct u16', 'distinct all'))
    for sig, n in sig_all.most_common(20):
        dv = len(sig_vals[sig])
        print('  %-16s %8d %8s %10d %10s'
              % (sig, n, '-', dv, '-'))

    print()
    print('=== verdict ===')
    strong_pal = [s for s in sig_pal if sig_pal[s] / sig_all[s] > 0.5
                  and sig_all[s] >= 20]
    strong_sty = [s for s in sig_sty if sig_sty[s] / sig_all[s] > 0.5
                  and sig_all[s] >= 20]
    if strong_pal:
        print('  M1 supported: %s carry a palette id' % ', '.join(strong_pal))
    else:
        print('  M1 not supported: no property carries a palette id reliably.')
    if strong_sty:
        print('  M2 supported: %s carry a style index' % ', '.join(strong_sty))
    else:
        print('  M2 not supported: no property carries a style index reliably.')
    if not strong_pal and not strong_sty:
        print()
        print('  That leaves M3 -- the colour reference is compiled into the')
        print('  rendering code and the resource files never name a colour.')
        print('  That would explain why the guides follow 0x400c while no view')
        print('  file appears to reference it, and it is only testable against')
        print('  the engine binary on the SD card.')


if __name__ == '__main__':
    main()
