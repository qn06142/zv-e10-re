"""Which bytes take BOTH values in the corpus, and which are simply constant?

Correcting the previous survey
------------------------------
It printed BOOLEAN next to bytes like `1b572204010e +0 = 8:10581` -- a byte that
is 8 in every one of 10,581 instances across 213 files.  That is not a boolean,
it is a constant field.  Labelling it "safe" was wrong: the whole reason a
boolean flip is the safest possible edit is that the engine has already drawn
both values.  A field that is never anything but 8 is more likely reserved,
padding, or a fixed layout constant, and the engine may well index on it or
assume it.  Changing it is *undefined*, which is a different thing from safe.

So the categories are properly separated here:

  BOOLEAN   takes exactly 2 distinct values, both non-zero-ish, and both occur
            a meaningful number of times.  This is the safe tier.
  ENUM      takes a small set of small values.  Safe if the new value is one
            the corpus already shows elsewhere for the same signature.
  CONSTANT  one value everywhere.  NOT a safe target.  Excluded.
  WIDE      many distinct values.  Geometry, ids, or lengths.  Tier 2 or unsafe.

The discriminator between BOOLEAN and CONSTANT is the ratio of the rarer value,
not the number of distinct values.  A byte with 10,580 ones and 1 zero is
effectively a constant with a typo somewhere.

And the target screen matters as much as the byte.  viewDummyBlack.uxc, which
the previous run picked, is a 148-byte "dummy black" placeholder -- flipping a
byte in it is safe but will show nothing, because the screen is probably not
displayed.  That is a wasted boot cycle.  The screen has to be one the user can
actually navigate to, so the candidate list is filtered for files whose names
correspond to real, reachable UI.

Nothing is written.  This produces a ranked shortlist with the actual value
distributions, so a choice can be made on evidence.
"""
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import uxc_safe as S

TGZ = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz')

# screens a user can plausibly reach and recognise
REACHABLE = [
    'viewSettingMenu', 'viewGlobalMenu', 'viewQuickNavi', 'viewFnMenu',
    'viewFocusArea', 'viewShootingInfoDisp', 'viewVersionNumber',
    'viewCopyrightInformation', 'viewVolume', 'viewCleaningMode',
    'viewRating', 'viewWhiteBalance', 'viewFormat', 'viewFocusMode',
    'viewDriveMode', 'viewHelpGuide', 'viewInitialSetting', 'viewRecovery',
    'viewPlayBack', 'viewMoviePreview', 'viewPhotoCapture', 'viewModeButton',
]


def load(only_prefix='view'):
    t = tarfile.open(TGZ)
    out = {}
    for m in t.getmembers():
        if not m.isfile() or not m.name.endswith('.uxc'):
            continue
        base = m.name.split('/')[-1]
        if not base.startswith(only_prefix):
            continue
        out[base] = t.extractfile(m).read()
    return out


def main():
    d = load()
    print('=== %d view files ===' % len(d))
    print()

    # (signature, payload offset) -> value counter, plus per-file presence
    vals = defaultdict(Counter)
    where = defaultdict(list)
    for name, b in sorted(d.items()):
        p = S.parse_view(b)
        for si, s in enumerate(p['sections']):
            for oi, o in enumerate(s['objects']):
                for pi, pr in enumerate(o['props']):
                    for i in range(pr['payload_len']):
                        k = (pr['sig'], i)
                        v = b[pr['payload_off'] + i]
                        vals[k][v] += 1
                        if len(where[k]) < 6:
                            where[k].append((name, si, oi, pi, o['class_id']))

    print('=' * 78)
    print('BOOLEAN: two values, both genuinely present')
    print('=' * 78)
    booleans = []
    for k, c in vals.items():
        n = sum(c.values())
        if n < 200 or len(c) != 2:
            continue
        (v1, c1), (v2, c2) = c.most_common(2)
        rare = min(c1, c2)
        ratio = rare / n
        if ratio < 0.01:
            continue                     # effectively a constant with a typo
        booleans.append((ratio, n, k, c))
    booleans.sort(reverse=True)
    print('  %-16s %5s %8s %6s  %s' % ('signature', 'off', 'total', 'min%', 'values'))
    for ratio, n, (sig, off), c in booleans[:22]:
        print('  %-16s %5d %8d %5.1f%%  %s'
              % (sig, off, n, 100 * ratio,
                 ' '.join('%d:%d' % (v, k) for v, k in c.most_common())))
    print()
    print('  %d boolean-like payload bytes corpus-wide' % len(booleans))
    print()

    print('=' * 78)
    print('CONSTANT bytes -- explicitly NOT targets')
    print('=' * 78)
    const = [(k, c) for k, c in vals.items()
             if len(c) == 1 and sum(c.values()) >= 500]
    print('  %d payload bytes take a single value across 500+ occurrences.' % len(const))
    print('  Examples, to show why the earlier label was wrong:')
    shown = 0
    for k, c in sorted(const, key=lambda kv: -sum(kv[1].values()))[:6]:
        v, n = c.most_common(1)[0]
        print('    %-16s +%-3d  always %d  (n=%d)' % (k[0], k[1], v, n))
    print()
    print('  A field that is one value in every instance is reserved or a')
    print('  layout constant.  The engine may assume it.  Not a safe target.')
    print()

    print('=' * 78)
    print('reachable screens containing a real boolean')
    print('=' * 78)
    bset = {k for _r, _n, k, _c in booleans}
    rows = []
    for pref in REACHABLE:
        for name, b in sorted(d.items()):
            if not name.startswith(pref):
                continue
            p = S.parse_view(b)
            nobj = sum(len(s['objects']) for s in p['sections'])
            hits = []
            for si, s in enumerate(p['sections']):
                for oi, o in enumerate(s['objects']):
                    for pi, pr in enumerate(o['props']):
                        for i in range(pr['payload_len']):
                            if (pr['sig'], i) in bset:
                                v = b[pr['payload_off'] + i]
                                if v not in (0,):
                                    hits.append((si, oi, pi, pr['sig'], i, v))
            if hits:
                rows.append((len(hits), name, len(b), nobj, hits))
    rows.sort(key=lambda r: (-r[0], r[2]))
    for nhits, name, sz, nobj, hits in rows[:18]:
        print()
        print('  %-34s %7d B  %3d objects  %3d boolean bytes' % (name[:34], sz, nobj, nhits))
        for si, oi, pi, sig, i, v in hits[:5]:
            print('     sec %d obj %d prop %d  %s +%d = %d' % (si, oi, pi, sig, i, v))
    if not rows:
        print('  (none -- reachable screens carry no non-zero booleans)')
    print()
    print('  Note the "v != 0" filter: a boolean that is already 1 is a')
    print('  candidate to flip to 0.  A boolean that is 0 everywhere is a')
    print('  constant, per the argument above.')


if __name__ == '__main__':
    main()
