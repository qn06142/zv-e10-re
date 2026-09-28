"""Find the lowest-risk edit that is still visible, and prove it is safe.

The safety argument, stated before the search so the search cannot bias it
---------------------------------------------------------------------
av-cam.bin lives on nflasha3 (/system, vfat).  The view resources live in
/usr/share/app on nflasha15 (/usr, ext2).  Different partition, and data rather
than code: a malformed view file cannot corrupt av-cam.bin.  So the "it would
brick the firmware" worry does not apply to this class of edit.

The real hazard is narrower.  Three outcomes are possible and only the third is
dangerous:

  the engine draws nonsense                 -> ugly, survivable
  the engine rejects the file, falls back   -> invisible
  the engine trusts a value and faults      -> crash, possibly a boot loop

Only values that change a LENGTH, or push geometry somewhere absurd, can reach
the third outcome.  Changing a value in place, within the range the corpus
already exercises, cannot make the renderer do anything it has not already done
a million times.  So the risk ranking is:

  1. boolean / small enum value   safest    the engine already handles both
  2. in-range geometry value      safe      no length change, bounded extent
  3. anything length-bearing      unsafe   excluded by construction

This searches for tier 1 first and reports what it finds.  It does not write.

How candidates are found
------------------------
A candidate is a property payload byte whose value, across the whole corpus, is
drawn from a tiny set.  If a byte only ever takes 0 and 1, it is a boolean.  If
it takes a handful of small values, it is an enum.  Both are the safe tier.

The null model matters: small byte values are common in *every* format, so a
byte being 0 or 1 proves nothing by itself.  The discriminator is whether the
*same signature* is small-valued in a structurally coherent way -- same object
class, same position, correlated with other properties -- and whether a
plausible alternative reading (a length field, a count) can be excluded.

The exclusion test is the important one: for a candidate byte, check whether
any other offset in the same property already encodes a length that would change
if this byte changed.  If a byte is immediately followed by a count, changing it
desynchronises the parse.  uxc_safe.propose_edit then proves the whole file
still parses identically, so anything that would desync is rejected
automatically rather than by my judgement.
"""
import struct
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

import uxc_safe as S

TGZ = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz')
OUT = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\app')


def load(only=None):
    """View resources only.  The .uxc set also contains color_cmn.uxc,
    lang_cmn.uxc and the per-language string_*.uxc files, which are not view
    containers and have no section/object grammar -- parse_view correctly
    rejects them, so they are filtered out here rather than being caught."""
    t = tarfile.open(TGZ)
    out = {}
    for m in t.getmembers():
        if not m.isfile() or not m.name.endswith('.uxc'):
            continue
        base = m.name.split('/')[-1]
        if not base.startswith('view'):
            continue
        if only and not any(base.startswith(p) for p in only):
            continue
        out[base] = t.extractfile(m).read()
    return out


def survey(d):
    """Value distributions per (signature, payload offset)."""
    print('=' * 78)
    print('byte-value survey: which payload bytes are boolean-like corpus-wide?')
    print('=' * 78)
    stats = defaultdict(lambda: {'n': 0, 'vals': Counter(), 'files': set()})
    for name, b in sorted(d.items()):
        p = S.parse_view(b)
        for s in p['sections']:
            for o in s['objects']:
                for pr in o['props']:
                    k = (pr['sig'], pr['payload_off'] - pr['off'])
                    st = stats[k]
                    st['n'] += 1
                    st['files'].add(name)
                    for i in range(pr['payload_len']):
                        v = b[pr['payload_off'] + i]
                        st['vals'][(k[1] - 6 + i, v)] += 1
    # aggregate: for each (sig, rel offset within payload) count distinct values
    agg = defaultdict(Counter)
    cnt = defaultdict(int)
    fileset = defaultdict(set)
    for (sig, rel), st in stats.items():
        for (off, v), c in st['vals'].items():
            agg[(sig, off)][v] += c
            cnt[(sig, off)] += c
            fileset[(sig, off)].add(rel)  # placeholder, replaced below
    # recompute cleanly: per (sig, byte offset in payload)
    agg2 = defaultdict(Counter)
    tot2 = defaultdict(int)
    fset2 = defaultdict(set)
    for name, b in sorted(d.items()):
        p = S.parse_view(b)
        for s in p['sections']:
            for o in s['objects']:
                for pr in o['props']:
                    for i in range(pr['payload_len']):
                        key = (pr['sig'], i)
                        agg2[key][b[pr['payload_off'] + i]] += 1
                        tot2[key] += 1
                        fset2[key].add(name)
    print()
    print('  %-16s %5s %7s %7s %s' % ('signature', 'off', 'count', 'files', 'value set'))
    rows = []
    for key, c in agg2.items():
        rows.append((len(c), key, c, tot2[key], len(fset2[key])))
    rows.sort(key=lambda r: (r[0], -r[3]))
    for nd, (sig, off), c, tot, nf in rows[:34]:
        vals = ' '.join('%d:%d' % (v, n) for v, n in c.most_common(10))
        flag = 'BOOLEAN' if nd <= 2 and tot >= 100 else ''
        if nd <= 8 and tot >= 200 and not flag:
            flag = 'enum'
        print('  %-16s %5d %7d %7d %-40s %s' % (sig, off, tot, nf, vals, flag))
    return agg2, tot2, fset2


def candidate_edit(d, name, sig, pred_off, new_value):
    """Propose a one-byte edit and let uxc_safe prove it structure-preserving."""
    b = d[name]
    p = S.parse_view(b)
    hits = []
    for si, s in enumerate(p['sections']):
        for oi, o in enumerate(s['objects']):
            for pi, pr in enumerate(o['props']):
                if pr['sig'] != sig:
                    continue
                if not (pr['payload_off'] + pred_off <
                        pr['payload_off'] + pr['payload_len']):
                    continue
                off = pr['payload_off'] + pred_off
                if b[off] == new_value:
                    continue
                hits.append((si, oi, pi, off, o, pr))
    if not hits:
        return None
    si, oi, pi, off, o, pr = hits[0]
    print()
    print('  candidate: %s  class %08x  object %08x  prop[%d] sig %s'
          % (name, o['class_id'], o['object_id'], pi, sig))
    print('    object @0x%04x, property @0x%04x, payload byte @0x%04x'
          % (o['off'], pr['off'], off))
    print('    %02x -> %02x' % (b[off], new_value))
    print('    object has %d properties; section has %d objects'
          % (o['property_count'], len(p['sections'][si]['objects'])))
    try:
        nb = S.propose_edit(b, off, new_value)
    except ValueError as e:
        print('    REJECTED: %s' % e)
        return None
    changed = sum(1 for x, y in zip(b, nb) if x != y)
    print('    ACCEPTED: %d byte differs, length %d -> %d, re-parse identical'
          % (changed, len(b), len(nb)))
    return dict(file=name, off=off, old=b[off], new=new_value, data=nb)


def main():
    d = load()
    print('=== %d view files ===' % len(d))
    print()
    print('  (view*.uxc only: color_cmn.uxc, lang_cmn.uxc and string_*.uxc are')
    print('   uxc containers but have no section/object grammar)')
    print()
    agg, tot, fset = survey(d)

    print()
    print('=' * 78)
    print('tier-1 candidates: booleans, and what they might be')
    print('=' * 78)
    booleans = [(k, c) for k, c in agg.items() if len(c) <= 2 and tot[k] >= 100]
    booleans.sort(key=lambda x: -tot[x[0]])
    for (sig, off), c in booleans[:10]:
        print('  %-16s payload+%d  %s  n=%d'
              % (sig, off, dict(c.most_common()), tot[(sig, off)]))
    print()
    print('  c34c39a70111 is the documented 0/1 scalar.  Finding it in a small,')
    print('  frequently-visited screen is the safest possible first edit: the')
    print('  engine has already drawn both values thousands of times.')
    print()

    # pick the smallest, simplest screen that contains a boolean
    print('=' * 78)
    print('which small screens contain booleans?  smallest first')
    print('=' * 78)
    rows = []
    for name, b in sorted(d.items()):
        if len(b) > 4000:
            continue
        p = S.parse_view(b)
        nbool = 0
        nobj = 0
        for s in p['sections']:
            for o in s['objects']:
                nobj += 1
                for pr in o['props']:
                    if pr['sig'] == 'c34c39a70111' and pr['payload_len'] == 1:
                        nbool += 1
        if nbool:
            rows.append((nbool, nobj, len(b), name))
    rows.sort()
    for nbool, nobj, sz, name in rows[:14]:
        print('  %-40s %7d B  %3d objects  %3d booleans' % (name[:40], sz, nobj, nbool))
    print()
    if not rows:
        print('  (no small screen with booleans)')
        return

    # the very safest edit we can propose: a boolean in the smallest screen
    target = rows[0][3]
    print('=' * 78)
    print('proposing an edit to %s' % target)
    print('=' * 78)
    b = d[target]
    p = S.parse_view(b)
    for s in p['sections']:
        for o in s['objects']:
            for pr in o['props']:
                if pr['sig'] == 'c34c39a70111' and pr['payload_len'] == 1:
                    off = pr['payload_off']
                    nv = 0 if b[off] == 1 else 1
                    r = candidate_edit(d, target, 'c34c39a70111', 0, nv)
                    if r:
                        OUT.mkdir(parents=True, exist_ok=True)
                        p2 = OUT / ('bool_%s' % target)
                        p2.write_bytes(r['data'])
                        print('    written for review: %s' % p2)
                        print('    (NOT pushed to the camera)')
                        return
    print('  no boolean found to edit')


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    main()
