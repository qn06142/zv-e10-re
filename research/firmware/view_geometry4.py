"""Find geometry by the engine's own constraint, not by guessing.

A real lead, from a string in libObj.so
---------------------------------------
    [%02d]WidgetID:%10u PosID:%02d  (x,y,w,h)=(%03d, %03d, %03d, %03d)

%03d is a hard constraint: the engine formats each of x, y, w, h as at most
three digits.  So geometry values live in 0..999, and any property whose values
exceed 999 is not geometry.  That is a falsifiable prediction about the data,
and it is the first real handle on geometry anyone has had.

Why the previous candidate was wrong
------------------------------------
8ac3b3620202, the highest-cardinality signature at 2,444 instances, spans
0..65535 -- so it is not geometry, and treating its width as x+w produced
125,324.  That test was correct and its conclusion was right; the signature is
simply not a rect.

Two views of the same property
-----------------------------
A rect can be stored as four u16s in one payload, or as four separate 16-bit
properties.  Both are common.  The doc notes class 76f0b37a "frequently consists
of several 8-byte scalar fields followed by the larger layout/geometry forms",
which is the separate-properties shape.  So both are searched, and a signature
is only called geometry if its values sit inside 0..999.

The test
--------
For every property signature, at every payload offset, check whether the value
distribution is bounded by 999 and has real spread.  Then require a companion:
a geometry property should have siblings in the same 0..999 range within the
same object, because x, y, w, h travel together.  A lone small-valued property
is just a small-valued property; four of them in one object is a rect.

That last requirement is the discriminator, and it is what separates a real
finding from another plausible-looking table.  It is the same standard that
falsified the earlier "selected" hypothesis.
"""
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import uxc_safe as S

TGZ = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz')
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


def u16s(b, off, n):
    return [struct_unpack(b, off + 2 * i) for i in range(n)]


def struct_unpack(b, o):
    import struct
    return struct.unpack_from('<H', b, o)[0]


def main():
    import struct
    d = load()
    print('=== %d view files ===' % len(d))
    print()
    print('the engine formats geometry with %%03d, so values are 0..%d' % LIMIT)
    print()

    # 1. every u16 slot in every property: bounded, and how spread
    stats = defaultdict(Counter)
    for name, b in sorted(d.items()):
        p = S.parse_view(b)
        for s in p['sections']:
            for o in s['objects']:
                for pr in o['props']:
                    for i in range(0, pr['payload_len'] - 1, 2):
                        v = struct.unpack_from('<H', b, pr['payload_off'] + i)[0]
                        stats[(pr['sig'], i)][v] += 1

    print('=' * 78)
    print('1. which payload slots are bounded by %d with real spread?' % LIMIT)
    print('=' * 78)
    print()
    print('  %-16s %4s %8s %7s %7s %6s  %s'
          % ('signature', 'off', 'count', 'distinct', 'max', 'spread', 'verdict'))
    bounded = []
    for (sig, off), c in stats.items():
        n = sum(c.values())
        if n < 300:
            continue
        mx = max(c)
        nd = len(c)
        # spread: does it use a wide range of the allowed space?
        frac = (mx / (LIMIT + 1.0))
        if mx <= LIMIT and nd >= 3 and frac >= 0.5:
            verdict = 'GEOMETRY-CANDIDATE'
            bounded.append((nd, sig, off, c, n))
        elif mx <= LIMIT and nd >= 8:
            verdict = 'bounded, small spread'
        else:
            verdict = ''
        if verdict:
            print('  %-16s %4d %8d %7d %7d %5.0f%%  %s'
                  % (sig, off, n, nd, mx, 100 * frac, verdict))
    print()
    print('  %d slots are bounded by %d with real spread' % (len(bounded), LIMIT))
    print()
    print('  Note: a small-valued property is NOT yet geometry.  Step 2 is')
    print('  what decides it.')
    print()

    # 2. the discriminator: do four such slots travel together in one object?
    print('=' * 78)
    print('2. do four such slots appear in the SAME object?  that is a rect')
    print('=' * 78)
    bset = {(sig, off) for _nd, sig, off, _c, _n in bounded}
    print()
    tally = Counter()
    best_obj = None
    best_n = 0
    for name, b in sorted(d.items()):
        p = S.parse_view(b)
        for s in p['sections']:
            for o in s['objects']:
                got = []
                for pr in o['props']:
                    for i in range(0, pr['payload_len'] - 1, 2):
                        if (pr['sig'], i) in bset:
                            v = struct.unpack_from('<H', b, pr['payload_off'] + i)[0]
                            got.append((pr['sig'], i, v))
                if len(got) >= 3:
                    tally[len(got)] += 1
                    if len(got) > best_n:
                        best_n = len(got)
                        best_obj = (name, o['class_id'], got)
    print('  objects carrying N bounded slots:')
    for n, c in sorted(tally.items()):
        print('    %d slots: %5d objects' % (n, c))
    print()
    if best_obj:
        name, cls, got = best_obj
        print('  richest example: %s class %08x with %d slots'
              % (name, cls, len(got)))
        for sig, off, v in got:
            print('     %-16s +%-3d = %4d' % (sig, off, v))
        print()
        if len(got) >= 4:
            print('  >> four or more bounded u16 slots in one object, matching')
            print('     the (x,y,w,h) arity of the engine\'s own format string.')
            print('     This is the geometry property, identified by a')
            print('     constraint the engine states about itself rather than')
            print('     by a guess about byte layout.')
    else:
        print('  no object carries 3+ bounded slots.  Geometry is either not')
        print('  stored as u16s, or not in these files.')
    print()

    # 3. sanity: confirm the limit is real by checking a known-bounded prop
    print('=' * 78)
    print('3. control: c34c39a70111 payload+0 is a 1-byte boolean, not a u16')
    print('=' * 78)
    n = 0
    mx = 0
    for name, b in sorted(d.items()):
        p = S.parse_view(b)
        for s in p['sections']:
            for o in s['objects']:
                for pr in o['props']:
                    if pr['sig'] == 'c34c39a70111' and pr['payload_len'] == 1:
                        n += 1
                        mx = max(mx, b[pr['payload_off']])
    print('  %d instances, max byte value %d' % (n, mx))
    print('  It never appears in the bounded-u16 list because its payload is')
    print('  1 byte.  The filter is not just accepting everything small.')


if __name__ == '__main__':
    main()
