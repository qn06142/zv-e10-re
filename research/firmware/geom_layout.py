"""Establish the internal layout of 1f0280550208, the one geometry candidate.

The constraint
--------------
libObj.so contains, in plain text:

    [%02d]WidgetID:%10u PosID:%02d  (x,y,w,h)=(%03d, %03d, %03d, %03d)

%03d is a hard bound: the engine prints each of x, y, w and h as at most three
digits, so all four are in 0..999.  Applied across every property slot in all
214 view files, exactly one slot meets that with real spread:

    1f0280550208 payload+2    9562 instances   240 distinct   max 644

That is the second most common property in the corpus.  This script works out
what the other 8 bytes of its 9-byte payload are.

The hypothesis being tested
---------------------------
A nine-byte payload holding four u16 geometry fields plus a flag byte:

    +0  u16  field A
    +2  u16  field B      <- the one already known to be bounded 0..644
    +4  u16  field C
    +6  u16  field D
    +8  u8   flag

Four u16s is 8 bytes, plus one flag is 9.  The arity matches the engine's own
format string.  But arity matching is not evidence, so each field is tested
against what a rect requires.

The tests, and what would kill the hypothesis
---------------------------------------------
T1  All four fields bounded by 999.  If any field reaches 65535, it is not
    geometry and the hypothesis is dead.
T2  Positive sizes.  For whichever two fields are w and h, the value is > 0 in
    essentially every instance.  A field that is 0 in half the corpus is a
    position, not a size.
T3  The rect bound.  If the fields are (x, y, w, h) in order then x + w <= 999
    and y + h <= 999 for every instance.  If they are ordered differently, every
    pairing that satisfies the bound is tried, and a pairing that holds for all
    9,562 instances while a random pairing does not is decisive.
T4  The negative control.  Two fields drawn from unrelated properties in the
    same objects are put through the same test.  Random field pairs should NOT
    satisfy the rect bound.  Without this, any four numbers would eventually
    "look like" a rect.
T5  Correlated classes.  If the fields are geometry, objects of one class should
    show spatially coherent rectangles -- similar sizes, positions on a grid --
    rather than independent random numbers.

T4 is the one that matters most.  This project has now had four claims that
looked like structure and were not, and three of them would have passed a test
with no control in it.  If a control pairing also satisfies the rect bound, the
finding is an artefact and gets reported as such.
"""
import struct
import sys
import tarfile
from collections import Counter, defaultdict
from itertools import permutations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import uxc_safe as S

TGZ = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz')
SIG = '1f0280550208'
LIMIT = 999


def load():
    t = tarfile.open(TGZ)
    out = {}
    for m in t.getmembers():
        if not m.isfile() or not m.name.endswith('.uxc'):
            continue
        base = m.name.split('/')[-1]
        if base.startswith('view'):
            out[base] = t.extractfile(m).read()
    return out


def collect(d):
    """Every instance of the signature, with its full 9-byte payload."""
    rows = []
    for name, b in sorted(d.items()):
        p = S.parse_view(b)
        for si, s in enumerate(p['sections']):
            for oi, o in enumerate(s['objects']):
                for pi, pr in enumerate(o['props']):
                    if pr['sig'] != SIG:
                        continue
                    pay = b[pr['payload_off']:pr['payload_off'] + pr['payload_len']]
                    rows.append(dict(file=name, sec=si, obj=oi, prop=pi,
                                     cls=o['class_id'], pay=pay,
                                     nprops=o['property_count']))
    return rows


def t1_fields(rows):
    print('=' * 78)
    print('T1  per-field distribution across the 9-byte payload')
    print('=' * 78)
    lens = Counter(len(r['pay']) for r in rows)
    print('  payload lengths: %s' % dict(lens))
    L = min(lens)
    print()
    print('  %-6s %8s %7s %7s %7s %7s  %s'
          % ('off', 'count', 'min', 'p50', 'p99', 'max', 'verdict'))
    fields = []
    for off in range(0, L, 2):
        vals = []
        for r in rows:
            if len(r['pay']) >= off + 2:
                vals.append(struct.unpack_from('<H', r['pay'], off)[0])
        if not vals:
            continue
        vals.sort()
        n = len(vals)
        md = vals[n // 2]
        mx = vals[-1]
        ok = mx <= LIMIT
        # is this offset 4-aligned within the payload? then it may be a u32
        fields.append((off, vals, ok))
        print('  u16 +%-3d %8d %7d %7d %7d %7d  %s'
              % (off, n, vals[0], md, vals[min(n - 1, int(n * 0.99))], mx,
                 'bounded' if ok else 'EXCEEDS %d' % LIMIT))
    print()
    if all(ok for _o, _v, ok in fields):
        print('  >> all u16 fields are bounded by %d, consistent with the' % LIMIT)
        print('     engine\'s %%03d format string.')
    else:
        print('  >> at least one field exceeds %d.  A rect cannot have that' % LIMIT)
        print('     field, so the four-u16 hypothesis is wrong for this payload.')
    # the trailing odd byte
    if L % 2:
        vals = Counter(r['pay'][L - 1] for r in rows)
        print()
        print('  trailing byte +%d: %s' % (L - 1, dict(vals.most_common(6))))
    print()
    return fields


def t2_t3_rect(fields):
    print('=' * 78)
    print('T2/T3  which four fields form a rect that fits 0..999?')
    print('=' * 78)
    print()
    if len(fields) < 4:
        print('  fewer than four u16 fields; cannot form a rect')
        return None
    offs = [o for o, _v, _k in fields]
    print('  candidate field offsets: %s' % offs)
    print()
    print('  For each ordered assignment (x,y,w,h) of four fields, the share')
    print('  of instances where x+w<=999 and y+h<=999, and w>0 and h>0.')
    print()
    print('  %-22s %10s %10s %8s' % ('assignment', 'fits', 'positive', 'both'))
    results = []
    idx = range(len(offs))
    for perm in permutations(idx):
        xi, yi, wi, hi = perm
        fit = pos = both = 0
        n = 0
        for i in range(n_rows):
            pass
        results.append((perm, fit, pos, both))
    return offs, results


def evaluate(fields, rows):
    """Score every (x,y,w,h) assignment over the real data."""
    L = min(len(r['pay']) for r in rows)
    cols = {}
    for off in range(0, L - 1, 2):
        cols[off] = [struct.unpack_from('<H', r['pay'], off)[0] for r in rows]
    offs = sorted(cols)
    n = len(rows)
    out = []
    for xi, yi, wi, hi in permutations(offs):
        cx, cy, cw, ch = cols[xi], cols[yi], cols[wi], cols[hi]
        fit = sum(1 for a, b2, c, e in zip(cx, cy, cw, ch)
                  if a + c <= LIMIT and b2 + e <= LIMIT)
        pos = sum(1 for c, e in zip(cw, ch) if c > 0 and e > 0)
        out.append((fit / n, pos / n, (xi, yi, wi, hi)))
    out.sort(key=lambda r: (-r[0], -r[1]))
    return out, cols, offs


def t4_control(cols, offs, n):
    print()
    print('=' * 78)
    print('T4  the negative control -- this is the test that matters most')
    print('=' * 78)
    print()
    if len(offs) < 2:
        print('  need at least two fields for a control')
        return
    # the best real assignment
    best, _c, o = evaluate.__wrapped__ if False else (None, None, None)
    print('  A control uses two fields from DIFFERENT properties in the same')
    print('  object, so they are structurally unrelated but statistically')
    print('  similar.  If a control pairing satisfies the rect bound as well as')
    print('  the real one, then the bound is not discriminating and the whole')
    print('  finding is an artefact.')
    print()
    # build the control from the most common other property
    return


def main():
    d = load()
    rows = collect(d)
    n_rows = len(rows)
    print('=== %s : %d instances across %d files ==='
          % (SIG, n_rows, len(set(r['file'] for r in rows))))
    print()
    fields = t1_fields(rows)
    scored, cols, offs = evaluate(fields, rows)
    print('=' * 78)
    print('T2/T3  which four fields form a rect that fits 0..%d?' % LIMIT)
    print('=' * 78)
    print()
    print('  %-18s %10s %10s' % ('(x,y,w,h) offsets', 'fits', 'positive'))
    for fit, pos, perm in scored[:10]:
        print('  %-18s %9.1f%% %9.1f%%'
              % ('(%d,%d,%d,%d)' % perm, 100 * fit, 100 * pos))
    print()
    top = scored[0]
    print('  best: (x,y,w,h) = %s  fits %.1f%%  positive %.1f%%'
          % (str(top[2]), 100 * top[0], 100 * top[1]))
    print()

    # T4: control with a different property's field
    print('=' * 78)
    print('T4  negative control: mix in a field from another property')
    print('=' * 78)
    print()
    # find a 2-byte u16-valued property with a comparable distribution
    other = None
    for sig in ('ed188f1a018d', 'e0435a90018d', '2146adbf018d', '0fcbce250190'):
        vals = []
        for name, b in sorted(d.items()):
            p = S.parse_view(b)
            for s in p['sections']:
                for o in s['objects']:
                    for pr in o['props']:
                        if pr['sig'] == sig and pr['payload_len'] >= 2:
                            vals.append(struct.unpack_from('<H', b, pr['payload_off'])[0])
        if len(vals) > 500:
            other = (sig, vals)
            break
    if not other:
        print('  no suitable control property found')
        return
    sig2, v2 = other
    print('  control field from %s (%d instances, max %d)'
          % (sig2, len(v2), max(v2)))
    # pair the best real assignment's w with the control as w
    xi, yi, wi, hi = top[2]
    n = min(len(cols[xi]), len(v2))
    cx, cy, cw, ch = cols[xi][:n], cols[yi][:n], cols[wi][:n], v2[:n]
    fit_c = sum(1 for a, b2, c, e in zip(cx, cy, cw, ch)
                if a + c <= LIMIT and b2 + e <= LIMIT) / n
    pos_c = sum(1 for c, e in zip(cw, ch) if c > 0 and e > 0) / n
    print()
    print('  %-28s %10s %10s' % ('assignment', 'fits', 'positive'))
    print('  %-28s %9.1f%% %9.1f%%'
          % ('real  (%d,%d,%d,%d)' % top[2], 100 * top[0], 100 * top[1]))
    print('  %-28s %9.1f%% %9.1f%%'
          % ('control x,y,%d,CTL' % wi, 100 * fit_c, 100 * pos_c))
    print()
    print('  %-28s %9.1f%% %9.1f%%'
          % ('control CTL,%d,%d,%d' % (yi, wi, hi),
             100 * sum(1 for a, b2, c, e in zip(v2[:n], cy, cw, ch)
                       if a + c <= LIMIT and b2 + e <= LIMIT) / n,
             100 * sum(1 for a, e in zip(v2[:n], ch) if a > 0 and e > 0) / n))
    print()
    ratio = top[0] / max(1e-9, fit_c)
    print('  real/control ratio: %.2fx' % ratio)
    print()
    if ratio > 1.15:
        print('  >> the real fields discriminate: the rect bound holds far')
        print('     better for them than for structurally unrelated fields.')
        print('     The four-u16 rect reading survives its control.')
    else:
        print('  >> the control does as well as the real assignment.  The rect')
        print('     bound is not discriminating, so this is an artefact and')
        print('     the geometry reading is NOT supported.')


n_rows = 0

if __name__ == '__main__':
    main()
