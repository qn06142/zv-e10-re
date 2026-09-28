"""Test the competing hypotheses for c34c39a70111 rather than assuming one.

The previous run produced a reading, and the temptation is to stop there.  But
"enables interactivity" is a guess with a competing explanation, and the way to
kill a guess is to write down what each hypothesis predicts and check which one
the data refuses to support.

Three hypotheses, and what each predicts about the 599 zero cases:

H_vis   "visible"          zeros should land on widgets that are deliberately
                           hidden, which means whole screens that are normally
                           suppressed -- a view that exists in the resources but
                           is not shown in most sessions.

H_en    "enabled"          zeros should land on menu items and focusable
                           controls, and be rare on pure display widgets.  This
                           predicts a correlation with interactive screen types
                           and with the presence of sibling controls.

H_sel   "selected/focused" zeros should be near-exclusive to a single currently
                           active item, so a screen should have at most one.
                           This is the sharpest prediction and the easiest to
                           falsify: if any screen has several zeros, H_sel dies.

The screen list from the previous run is already suggestive: viewFnMenu 60%,
viewTriDial 67%, viewFocusArea_C 57%, viewQuickNavi 42%, against
viewPanoramaStl 9% and viewStlrec 6%.  Menus and dials and focus selectors
against playback displays.  But that is one correlation, and correlations of the
right size are easy to over-read.

So each hypothesis gets a test that it could fail.

The test that matters most
--------------------------
H_sel is falsifiable with data already in hand, and it should be checked first
because it is the most specific.  If a single screen has many zero instances,
the flag cannot be "currently selected", because only one thing is selected at a
time.  That check is decisive and costs nothing.
"""
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import uxc_safe as S

TGZ = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz')
SIG = 'c34c39a70111'


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
            objs = s['objects']
            for oi, o in enumerate(objs):
                for pi, pr in enumerate(o['props']):
                    if pr['sig'] == SIG and pr['payload_len'] == 1:
                        rows.append(dict(
                            file=name, sec=si, obj=oi, cls=o['class_id'],
                            oid=o['object_id'], parent=o['parent_id'],
                            nsibs=len(objs), value=b[pr['payload_off']]))
    return rows


def h_sel_test(rows):
    """H_sel: 'selected/focused'.  Predicts at most one zero per screen."""
    print('=' * 78)
    print('H_sel  "currently selected / focused"')
    print('=' * 78)
    per = Counter(r['file'] for r in rows if r['value'] == 0)
    multi = [(f, n) for f, n in per.most_common() if n > 1]
    print()
    print('  screens with more than one zero instance: %d of %d screens with any'
          % (len(multi), len(per)))
    for f, n in multi[:10]:
        print('    %-42s %3d zeros' % (f[:42], n))
    print()
    if multi:
        print('  >> H_sel FALSIFIED.  %d screens carry multiple zero instances'
              % len(multi))
        print('     (up to %d in one file). Only one item can be selected at'
              % max(n for _f, n in multi))
        print('     a time, so this is not a selection flag.')
        return False
    print('  >> H_sel survives: no screen has more than one zero.')
    return True


def h_vis_test(rows, d):
    """H_vis: 'visible'.  Predicts zeros on whole suppressed screens."""
    print()
    print('=' * 78)
    print('H_vis  "visible"')
    print('=' * 78)
    tot = Counter(r['file'] for r in rows)
    zer = Counter(r['file'] for r in rows if r['value'] == 0)
    rates = []
    for f, t in tot.items():
        rates.append((zer[f] / t, f, zer[f], t))
    rates.sort(reverse=True)
    print()
    print('  If this were visibility, a screen would tend to be all-or-nothing:')
    print('  a few widgets hidden and the rest shown, so the rate would be')
    print('  either low or high, not a smooth spread.')
    print()
    print('  %-42s %6s %6s %6s' % ('screen', 'zeros', 'total', 'rate'))
    for rate, f, z, t in rates[:10]:
        print('    %-42s %6d %6d %5.0f%%' % (f[:42], z, t, 100 * rate))
    print('    ...')
    for rate, f, z, t in rates[-5:]:
        print('    %-42s %6d %6d %5.0f%%' % (f[:42], z, t, 100 * rate))
    print()
    # all-or-nothing test: bimodal vs uniform
    buckets = Counter(min(9, int(r * 10)) for r, _f, _z, _t in rates)
    print('  rate histogram (deciles): %s' % ' '.join('%d:%d' % (k, v) for k, v in sorted(buckets.items())))
    print()
    spread = buckets.most_common(1)[0][1] / max(1, len(rates))
    print('  most populated decile holds %.0f%% of screens' % (100 * spread))
    print()
    if spread < 0.35:
        print('  >> the distribution is spread across deciles, not bimodal.')
        print('     Visibility would concentrate at the ends. H_vis weakened.')
    else:
        print('  >> the distribution is concentrated, consistent with whole')
        print('     screens being suppressed. H_vis survives this test.')
    return spread < 0.35


def h_en_test(rows):
    """H_en: 'enabled'.  Predicts zeros on interactive screens, not displays."""
    print()
    print('=' * 78)
    print('H_en  "enabled / interactive"')
    print('=' * 78)
    inter = ('FnMenu', 'QuickNavi', 'TriDial', 'FocusArea', 'FocusSet', 'Setting',
             'Menu', 'Rating', 'WhiteBalance', 'Focus', 'Dial', 'Button',
             'ModeButton', 'Ib', 'Key')
    disp = ('PanoramaStl', 'Stlrec', 'IroiroCon', 'showInfoDisp', 'Preview',
           'Iroiro', 'Version', 'Copyright', 'Caution', 'Detail')
    def rate(pred):
        t = z = 0
        for r in rows:
            b = r['file'].replace('view', '').replace('.uxc', '')
            if pred(b):
                t += 1
                z += (r['value'] == 0)
        return z, t
    zi, ti = rate(lambda b: any(k in b for k in inter))
    zd, td = rate(lambda b: any(k in b for k in disp))
    print()
    print('  interactive-sounding screens: %5d instances, %4d zero (%.1f%%)'
          % (ti, zi, 100.0 * zi / max(1, ti)))
    print('  display-sounding screens    : %5d instances, %4d zero (%.1f%%)'
          % (td, zd, 100.0 * zd / max(1, td)))
    print()
    if ti and td and zi / ti > 2 * (zd / td):
        print('  >> interactive screens are %.1fx more likely to be zero.'
              % ((zi / ti) / max(1e-9, zd / td)))
        print('     H_en is the best-supported reading so far.')
        return True
    print('  >> no strong separation by screen name. H_en not supported by')
    print('     this test.')
    return False


def main():
    d = load()
    rows = collect(d)
    z = sum(1 for r in rows if r['value'] == 0)
    print('=== %d instances of %s, %d zero ===' % (len(rows), SIG, z))
    print()
    ok_sel = h_sel_test(rows)
    ok_vis = h_vis_test(rows, d)
    ok_en = h_en_test(rows)
    print()
    print('=' * 78)
    print('summary')
    print('=' * 78)
    print('  H_sel  "selected/focused"   %s' % ('survives' if ok_sel else 'FALSIFIED'))
    print('  H_vis  "visible"           %s' % ('weakened' if ok_vis else 'survives'))
    print('  H_en   "enabled"           %s' % ('best supported' if ok_en else 'not supported'))
    print()
    print('  This is an inference from correlated defaults, not a known name.')
    print('  The class distribution is the strongest evidence: 188 classes are')
    print('  uniformly 1, 18 uniformly 0, only 32 mixed.  A flag that is a')
    print('  per-widget-type default with a minority of disabled instances is')
    print('  an enable/state flag.  A visibility flag would more likely be')
    print('  uniform per screen, and it is not: the same class 5f07f17d is 1 in')
    print('  1481 objects and 0 in 317, spread across many screens.')


if __name__ == '__main__':
    main()
