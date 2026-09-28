"""Find the geometry properties, so the layout can actually be reshaped.

The colour path is closed: no view property carries a colour id, so view files
cannot be recoloured.  But the object layer is fully parsed -- 10640 objects with
derived boundaries and known signatures -- so geometry, visibility, z-order and
state are all reachable at exact offsets.  That is a bigger surface than colour
ever was, and this script works out which signatures are the coordinates.

The question is narrow and decidable: which property payloads are positions and
sizes?

Evidence that distinguishes geometry from an enum or a tag, in order of
strength:

G1  Range.  Screen coordinates live in a bounded, non-trivial interval, roughly
    0..2000 for x and 0..1500 for y on this class of panel.  A property whose
    values span 0..65535 is not a coordinate.  A property that is always 0..12
    is an enum.

G2  Structure.  Geometry comes in pairs or quads.  If a payload is two u16s
    where the first is usually large and the second usually small, that is
    (x, w) or (y, h).  If a payload is four u16s, that is a rect.

G3  The bounding-box test.  A (w, h) pair should have w and h each smaller than
    the panel and should not correlate with each other.  More usefully: a rect's
    right edge, x + w, should land inside the panel for nearly every object.  If
    a candidate 4-tuple has x + w <= panel_w for ~all instances, it is a rect.

G4  Per-class consistency.  A widget class has a fixed geometry unless the
    layout changed, so the same signature on the same class should have similar
    values.  A tag is constant per class; a coordinate varies with position in
    the layout.  Distinguishing "varies across the corpus" from "constant within
    a class" is the sharpest test available.

Nothing here writes anything.  It identifies the fields, and identifies a small
tasteful edit to try, with exact byte offsets.  The edit is the user's call.

Panel size is not assumed.  The largest observed coordinate pair is used to
bracket it, and if the data does not support a size the scripts do not invent
one.
"""
import struct
import tarfile
from collections import Counter, defaultdict
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


def objects(b):
    """Yield (class_id, obj_off, obj_end, [(sig, prop_off, payload)])."""
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
            nprop = b[st + 13]
            p = st + 14
            props = []
            for _k in range(nprop):
                if p >= oe:
                    break
                ln = prop_len(b, p)
                if ln is None or p + ln > oe:
                    break
                props.append((b[p:p + 6].hex(), p, b[p + 6:p + ln]))
                p += ln
            yield u32(b, st), st, oe, props


def main():
    t = tarfile.open(TGZ)
    views = {}
    for m in t.getmembers():
        if m.isfile() and '/view' in m.name and m.name.endswith('.uxc'):
            views[m.name.split('/')[-1]] = t.extractfile(m).read()

    # collect every u16 at every payload offset, per signature
    by_sig = defaultdict(list)          # sig -> list of (cls, objoff, tuple of u16s)
    nobj = 0
    for name, b in sorted(views.items()):
        for cls, st, oe, props in objects(b):
            nobj += 1
            for sig, off, pay in props:
                vals = tuple(struct.unpack_from('<H', pay, k)[0]
                             for k in range(0, len(pay) - 1, 2))
                by_sig[sig].append((cls, off, vals, len(pay) - 6))

    print('=== %d view files, %d objects, %d signatures ==='
          % (len(views), nobj, len(by_sig)))
    print()

    # panel size bracket: the largest plausible coordinate anywhere
    allv = []
    for sig, rows in by_sig.items():
        for _c, _o, vals, _pl in rows:
            allv.extend(vals)
    allv.sort()
    n = len(allv)
    print('=== value distribution across every u16 in every payload ===')
    print('  %d values; percentiles:' % n)
    for p in (0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99):
        print('    p%-5s %6d' % (p, allv[min(n - 1, int(n * p))]))
    print('    max    %6d' % allv[-1])
    print()
    print('  If geometry is present, the 75th-99th percentiles should cluster')
    print('  around plausible panel dimensions, not spread to 65535.')
    print()

    print('=== candidate geometry signatures ===')
    print('  %-16s %7s %6s %6s %-10s %-10s %s'
          % ('signature', 'occurs', 'words', 'p50', 'p90', 'p99', 'reading'))
    cands = []
    for sig, rows in by_sig.items():
        occ = len(rows)
        if occ < 20:
            continue
        words = rows[0][2]
        flat = sorted(v for _c, _o, vals, _p in rows for v in vals)
        if not flat:
            continue
        p50 = flat[len(flat) // 2]
        p90 = flat[int(len(flat) * 0.9)]
        p99 = flat[min(len(flat) - 1, int(len(flat) * 0.99))]
        # geometry reads: several words, values in a bounded non-trivial range
        if len(words) >= 2 and p99 <= 4096 and p99 > 200:
            cands.append((sig, occ, words, p50, p90, p99, rows))
    cands.sort(key=lambda r: -r[1])
    for sig, occ, words, p50, p90, p99, rows in cands[:20]:
        print('  %-16s %7d %6d %6d %-10d %-10d CANDIDATE'
              % (sig, occ, len(words), p50, p90, p99))
    if not cands:
        print('  (none)')
    print()

    # G2/G3: structure test on the top candidates
    for sig, occ, words, p50, p90, p99, rows in cands[:6]:
        print('  --- %s  (%d occ, %d words/payload) ---' % (sig, occ, len(words)))
        # what word positions carry the large values?
        for wi in range(len(words)):
            col = [vals[wi] for _c, _o, vals, _p in rows if wi < len(vals)]
            if not col:
                continue
            col.sort()
            print('     word %d: n=%-6d min %-5d p50 %-5d p90 %-5d max %-5d'
                  % (wi, len(col), col[0], col[len(col) // 2],
                     col[int(len(col) * 0.9)], col[-1]))
        # sample real instances
        print('     sample instances (class, file objoff, words):')
        for cls, off, vals, pl in rows[:6]:
            print('       cls %08x  obj 0x%04x  %s'
                  % (cls, off, ' '.join('%d' % v for v in vals)))
        # G4: does this vary within a class, or is it constant per class?
        bycls = defaultdict(set)
        for cls, off, vals, pl in rows:
            bycls[cls].add(vals)
        multi = sum(1 for c, s in bycls.items() if len(s) > 1)
        print('     classes %d, of which vary: %d  -> %s'
              % (len(bycls), multi,
                 'POSITION-LIKE (varies within a class)' if multi
                 else 'constant per class -> likely a tag or state'))
        print()

    # the 4-word candidates: rect test
    print('=== rect test: does a 4-word payload look like (x,y,w,h)? ===')
    for sig, occ, words, p50, p90, p99, rows in cands:
        if len(words) < 4:
            continue
        ok = 0
        tot = 0
        xs = []
        ws = []
        for cls, off, vals, pl in rows:
            if len(vals) < 4:
                continue
            x, y, w, h = vals[0], vals[1], vals[2], vals[3]
            tot += 1
            xs.append(x + w)
            ws.append(max(x, y, w, h))
            # weak sanity: sizes positive and not astronomically large
            if w > 0 and h > 0 and w < 4096 and h < 4096:
                ok += 1
        if tot:
            xs.sort()
            ws.sort()
            print('  %-16s %5d instances  w>0&&h>0 in %d (%.0f%%)'
                  % (sig, tot, ok, 100.0 * ok / tot))
            print('     max(x+w)=%d  p90=%d  max component=%d'
                  % (xs[-1], xs[int(len(xs) * 0.9)], ws[-1]))
    print()
    print('  A rect whose x+w never exceeds a plausible panel width, with')
    print('  w>0 and h>0 nearly always, is a rect.  Two independent conditions')
    print('  passing on the same signature is not a coincidence.')


if __name__ == '__main__':
    main()
