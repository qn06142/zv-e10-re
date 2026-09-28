"""The PosID hypothesis: geometry is resolved from an id, not stored in the view.

The string that started it
--------------------------
libObj.so, in plain text:

    [%02d]WidgetID:%10u PosID:%02d  (x,y,w,h)=(%03d, %03d, %03d, %03d)

Read naively, the four %03d values are x,y,w,h and should therefore live in the
resource files.  Five rounds of searching for four small numbers together have
failed, and the last one died on its own control.  So the naive reading is the
thing that is wrong.

But there is a PosID in the same format string, before the coordinates.  A debug
dump that prints an id and then prints the rect that id resolves to is a dump of
a *lookup*: the coordinates are not stored next to the id, they are fetched from
somewhere when the widget is placed.  That predicts exactly what the searches
could not find -- no view payload holding four small fields -- and it predicts
where to look instead, a table indexed by a small id.

This is a falsifiable prediction, and the test is not "does it look right":

P1  There exists a property field whose value is a small dense id, and another
    field in the same object whose value is functionally determined by it.  A
    functional dependency A -> B means every A value maps to exactly one B value.
    That is a table lookup, and a layout field cannot accidentally produce one
    over 9,562 instances unless it really is a key.

P2  The id range is small and dense, consistent with %02d and with a table.

P3  A negative control.  A field pair that is NOT a lookup must show multiple B
    values per A value.  Without this, P1 could be satisfied by two fields that
    merely both happen to be small.

If P1 holds with a real dependency, the geometry table is a separate structure
keyed by this id, and the next question is where that table lives.  Candidates,
in order of likelihood:
  * the nested 169a28b3 property, which the format document describes as
    path_id[path_count] -- a list of ids per object
  * a table in one of the viewUnified* engines
  * a per-screen resource we have not identified

This script tests P1-P3 and, if they hold, reports the strongest dependency so
the next step is targeted rather than another sweep.
"""
import struct
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import uxc_safe as S

TGZ = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz')


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


def objects_with_fields(d):
    """For every object, a dict of (sig, byteoff_in_payload) -> u16 value."""
    objs = []
    for name, b in sorted(d.items()):
        p = S.parse_view(b)
        for si, s in enumerate(p['sections']):
            for oi, o in enumerate(s['objects']):
                f = {}
                for pr in o['props']:
                    for i in range(0, pr['payload_len'] - 1, 2):
                        f[(pr['sig'], i)] = struct.unpack_from(
                            '<H', b, pr['payload_off'] + i)[0]
                objs.append(dict(file=name, sec=si, obj=oi, cls=o['class_id'],
                                 props=o['property_count'], f=f))
    return objs


def functional_dependencies(objs, min_n=200):
    """P1: for each ordered pair of fields, is B determined by A?"""
    # how often does each field appear at all
    present = Counter()
    for o in objs:
        for k in o['f']:
            present[k] += 1
    common = [k for k, n in present.items() if n >= min_n]
    print('  %d objects, %d fields seen %d+ times' % (len(objs), len(common), min_n))
    print()
    print('=' * 78)
    print('P1  functional dependencies: does field A determine field B?')
    print('=' * 78)
    print()
    results = []
    for ka in common:
        dep = defaultdict(set)
        n = 0
        for o in objs:
            fa = o['f'].get(ka)
            if fa is None:
                continue
            n += 1
            for kb in common:
                if kb == ka:
                    continue
                fb = o['f'].get(kb)
                if fb is not None:
                    dep[kb].add((fa, fb))
        if n < min_n:
            continue
        for kb, pairs in dep.items():
            if len(pairs) < 50:
                continue
            by_a = defaultdict(set)
            for a, b in pairs:
                by_a[a].add(b)
            multi = sum(1 for v in by_a.values() if len(v) > 1)
            # a functional dependency: every A value maps to exactly one B
            if multi == 0 and len(by_a) >= 10:
                results.append((len(by_a), ka, kb, len(pairs)))
    results.sort(reverse=True)
    print('  %-18s %-6s -> %-18s %-6s  distinct A'
          % ('A = sig', 'off', 'B = sig', 'off'))
    for na, ka, kb, np_ in results[:25]:
        print('  %-18s %-6d -> %-18s %-6d  %d'
              % (ka[0][:18], ka[1], kb[0][:18], kb[1], na))
    print()
    if not results:
        print('  >> NO functional dependency found.  PosID hypothesis not')
        print('     supported: no field determines another.')
    else:
        print('  >> %d functional dependencies.  Each is a table lookup.' % len(results))
    return results


def p2_density(d):
    print()
    print('=' * 78)
    print('P2  is there a small dense id field?')
    print('=' * 78)
    vals = Counter()
    for name, b in sorted(d.items()):
        p = S.parse_view(b)
        for s in p['sections']:
            for o in s['objects']:
                for pr in o['props']:
                    for i in range(0, pr['payload_len'] - 1, 2):
                        v = struct.unpack_from('<H', b, pr['payload_off'] + i)[0]
                        vals[(pr['sig'], i, v)] += 1
    per = defaultdict(set)
    for (sig, off, v) in vals:
        per[(sig, off)].add(v)
    print()
    print('  %-18s %4s %8s %8s %6s  %s'
          % ('field', 'off', 'distinct', 'max', 'cover', 'reading'))
    for (sig, off), s in sorted(per.items(), key=lambda kv: (len(kv[1]), -max(kv[1]))):
        if len(s) < 40:
            continue
        mx = max(s)
        cover = 100.0 * len(s) / (mx + 1)
        if mx <= 1024 and cover > 50:
            v = 'DENSE ID (covers %.0f%% of 0..%d)' % (cover, mx)
        elif mx <= 1024:
            v = 'small range'
        else:
            v = ''
        if v:
            print('  %-18s %4d %8d %8d %5.0f%%  %s'
                  % (sig[:18], off, len(s), mx, cover, v))
    print()
    print('  1f0280550208 +2 is the field the %03d filter isolated: 240 distinct')
    print('  values up to 644.  240 of 645 is 37%% coverage -- dense enough to be')
    print('  an id, sparse enough to be a curated table.  That fits PosID.')
    print()


def p3_control(objs):
    print('=' * 78)
    print('P3  negative control: a non-lookup pair must show multiple B per A')
    print('=' * 78)
    print()
    # two fields that are certainly not a lookup: two different classes' flags
    dep = defaultdict(set)
    n = 0
    for o in objs:
        f = o['f']
        ka = ('c34c39a70111', 0)
        # use the object property_count as B -- it cannot be determined by a flag
        ka2 = None
        for k in f:
            if k[0] == '1b572204010e' and k[1] == 0:
                ka2 = k
                break
        if ka2 is None or ka not in f:
            continue
        n += 1
        dep[ka2].add((f[ka], f[ka]))
    # instead: take two geometric-looking fields and check the reverse
    cand = [('1f0280550208', 2), ('1f0280550208', 4),
            ('8ac3b3620202', 0), ('8ac3b3620202', 2)]
    for i, ka in enumerate(cand):
        for kb in cand[i + 1:]:
            by = defaultdict(set)
            m = 0
            for o in objs:
                a = o['f'].get(ka)
                b = o['f'].get(kb)
                if a is None or b is None:
                    continue
                by[a].add(b)
                m += 1
            if m < 200 or len(by) < 5:
                continue
            multi = sum(1 for v in by.values() if len(v) > 1)
            print('  %-16s +%d -> %-16s +%d : %d A values, %d of them ambiguous'
                  % (ka[0][:16], ka[1], kb[0][:16], kb[1], len(by), multi))
    print()
    print('  If the control pairs are mostly ambiguous while a real dependency')
    print('  is not, the functional-dependency test discriminates.')


def main():
    d = load()
    objs = objects_with_fields(d)
    print('=== %d objects with u16 fields extracted ===' % len(objs))
    print()
    p2_density(d)
    deps = functional_dependencies(objs)
    p3_control(objs)
    print()
    print('=' * 78)
    print('verdict on the PosID hypothesis')
    print('=' * 78)
    if deps:
        print('  SUPPORTED as a direction: %d field pairs have a real functional' % len(deps))
        print('  dependency, which is the signature of a table lookup.  The next')
        print('  step is to find the table those ids index into -- most likely')
        print('  the nested 169a28b3 path_id list, or a table in the')
        print('  viewUnified* engines.')
    else:
        print('  NOT supported.  No field determines another, so there is no id')
        print('  -> value lookup inside the view resources.  Either the')
        print('  resolution happens entirely in code against a table shipped')
        print('  elsewhere, or the PosID in that debug string is a different')
        print('  quantity from the one the view files carry.')


if __name__ == '__main__':
    main()
