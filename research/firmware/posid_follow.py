"""Follow the dependency: 1b572204010e +8 determines fields in two other properties.

What the previous run found
---------------------------
24 functional dependencies among the 22 common u16 fields, and the two strongest
by arity are:

    1b572204010e +8   ->  1b572204010e +0   402 distinct A values
    1b572204010e +8   ->  1f0280550208 +0   402 distinct A values
    1b572204010e +2   ->  1b572204010e +0   245
    1f0280550208 +2   ->  1b5722040108 +4   240

Reading that carefully
-----------------------
1b572204010e is the most common property in the corpus: 10,581 instances,
16 bytes, so a 10-byte payload.  Its fields are:

    +0  always 0        (10,581 of 10,581)
    +2  always 0
    +5  always 8
    +6  always 0
    +7  always 0
    +8  402 distinct values   <- the only varying field

So +8 is the payload's only real content, and it indexes 402 distinct things.
That is a style, class, or layout-table id, and it is exactly the PosID shape.

And it determines fields in OTHER properties.  A field in property P1 that fixes
a field in property P2 means the engine does not read them independently: it
reads P1's id, looks something up, and P2's value is the result of that lookup.
That is a decoded pointer across properties.

Why this matters more than a bare id
------------------------------------
An id on its own does not tell us what to change.  A decoded pointer tells us the
resources already contain a join: if a view object's style id selects a row, and
that row is in a file we can edit, then editing that file restyles every object
that references it.  That is a far bigger lever than a per-object value edit, and
it is how a real redesign would work -- change a few dozen rows, not thousands
of objects.

So: establish the mapping.  For each value of 1b572204010e +8, what do the
dependent fields equal?  If the map is small and clean, the join is real and
the next step is finding the table it points into.  If it is noisy, the
dependency is a coincidence of a common value and I should say so.

The test, and its control
-------------------------
P1  the map from A to B is a function, and it is not a constant map.  A
    "dependency" where B never varies is not a dependency, it is B being
    fixed -- which is exactly the degenerate case the previous run's control
    accidentally demonstrated.  So the map must have B varying across A values.

P2  the reverse must not hold.  If B also determines A, the two fields are
    interchangeable and there is no join, just two views of one number.

P3  a control: two fields from the same object class that are known to be
    independent should show multiple B per A.  Without this, "a function from A
    to B" could be an artefact of both fields being small.
"""
import struct
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import uxc_safe as S

TGZ = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz')
A = ('1b572204010e', 8)


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
    rows = []
    for name, b in sorted(d.items()):
        p = S.parse_view(b)
        for si, s in enumerate(p['sections']):
            for oi, o in enumerate(s['objects']):
                f = {}
                for pr in o['props']:
                    for i in range(0, pr['payload_len'] - 1, 2):
                        f[(pr['sig'], i)] = struct.unpack_from(
                            '<H', b, pr['payload_off'] + i)[0]
                rows.append(dict(file=name, sec=si, obj=oi, cls=o['class_id'],
                                 f=f))
    return rows


def payload_bytes(d):
    """The full 10-byte payload of the anchor property, per instance."""
    out = []
    for name, b in sorted(d.items()):
        p = S.parse_view(b)
        for si, s in enumerate(p['sections']):
            for oi, o in enumerate(s['objects']):
                for pr in o['props']:
                    if pr['sig'] == A[0]:
                        out.append((name, o['class_id'],
                                    b[pr['payload_off']:pr['payload_off'] + pr['payload_len']]))
    return out


def main():
    d = load()
    rows = collect(d)
    print('=== %d objects ===' % len(rows))
    print()
    print('anchor: %s payload+8' % A[0])
    print()

    # P1: does A determine B, with B actually varying?
    print('=' * 78)
    print('P1  the map A -> B, and whether B varies')
    print('=' * 78)
    print()
    targets = [('1b572204010e', 0), ('1f0280550208', 0), ('1f0280550208', 4),
               ('1b572204010e', 2), ('1b572204010e', 6), ('1f0280550208', 2)]
    maps = {}
    for kb in targets:
        by = defaultdict(set)
        cnt = Counter()
        for o in rows:
            a = o['f'].get(A)
            b = o['f'].get(kb)
            if a is None or b is None:
                continue
            by[a].add(b)
            cnt[a] += 1
        if len(by) < 10:
            continue
        multi = sum(1 for v in by.values() if len(v) > 1)
        bvals = set()
        for v in by.values():
            bvals |= v
        # only count as a real dependency if B actually varies
        real = len(bvals) > 1 and multi == 0
        print('  A -> %-16s +%d : %4d A values, %3d B values, %d ambiguous   %s'
              % (kb[0][:16], kb[1], len(by), len(bvals), multi,
                 'REAL DEPENDENCY' if real else
                 ('B constant' if len(bvals) == 1 else 'ambiguous')))
        if real:
            maps[kb] = by
    print()
    if not maps:
        print('  >> no real dependency survives: every apparent one had B')
        print('     constant or ambiguous.  The previous run over-reported.')
        return
    print()

    # P2: is it a join, or two views of one number?
    print('=' * 78)
    print('P2  does B determine A back?  (a join, or one number twice?)')
    print('=' * 78)
    print()
    for kb in maps:
        rev = defaultdict(set)
        for a, bs in maps[kb].items():
            for b in bs:
                rev[b].add(a)
        multi = sum(1 for v in rev.values() if len(v) > 1)
        print('  %-16s +%d -> A : %4d B values, %d map back to >1 A   %s'
              % (kb[0][:16], kb[1], len(rev), multi,
                 'JOIN' if multi > 0 else 'bijective (not a join)'))
    print()

    # what does the map look like?
    print('=' * 78)
    print('the map itself, for the strongest dependency')
    print('=' * 78)
    kb = max(maps, key=lambda k: len(maps[k]))
    by = maps[kb]
    print('  A = %s +%d  ->  B = %s +%d' % (A[0], A[1], kb[0], kb[1]))
    print()
    print('  %-8s %-8s %s' % ('A value', 'count', 'B value'))
    for a in sorted(by)[:40]:
        n = sum(1 for o in rows if o['f'].get(A) == a and kb in o['f'])
        print('  %-8d %-8d %s' % (a, n, sorted(by[a])))
    if len(by) > 40:
        print('  ... %d more' % (len(by) - 40))
    print()

    # is B a simple function of A?  b = a - k, a >> n, a * k
    pairs = []
    for a, bs in by.items():
        if len(bs) == 1:
            pairs.append((a, next(iter(bs))))
    pairs.sort()
    print('  %d clean pairs. Testing simple relations:' % len(pairs))
    diffs = Counter(b - a for a, b in pairs)
    print('    b - a        : %s' % dict(diffs.most_common(5)))
    if diffs:
        (k, n), = diffs.most_common(1)
        if n > 0.7 * len(pairs):
            print('    >> b = a + %d for %d of %d (%.0f%%)'
                  % (k, n, len(pairs), 100.0 * n / len(pairs)))
    print()

    # P3: control
    print('=' * 78)
    print('P3  control: an independent pair must be ambiguous')
    print('=' * 78)
    print()
    ctl = [('1f0280550208', 6), ('8ac3b3620202', 0), ('8ac3b3620202', 2),
           ('e0435a90018d', 0)]
    for i, ka in enumerate(ctl):
        for kb2 in ctl[i + 1:]:
            by2 = defaultdict(set)
            m = 0
            for o in rows:
                a = o['f'].get(ka)
                b = o['f'].get(kb2)
                if a is None or b is None:
                    continue
                by2[a].add(b)
                m += 1
            if m < 200 or len(by2) < 5:
                continue
            multi = sum(1 for v in by2.values() if len(v) > 1)
            print('  %-16s +%d -> %-16s +%d : %4d A, %d ambiguous (%.0f%%)'
                  % (ka[0][:16], ka[1], kb2[0][:16], kb2[1], len(by2), multi,
                     100.0 * multi / len(by2)))
    print()
    print('  Control pairs that are mostly ambiguous confirm the test')
    print('  discriminates: a real dependency should be near 0%% and a')
    print('  coincidental one near 100%%.')


if __name__ == '__main__':
    main()
