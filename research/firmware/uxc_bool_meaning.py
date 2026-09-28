"""What does the boolean DO? Infer it from correlated defaults, not by flipping.

The objection
-------------
Proposing a boolean flip without knowing what the flag controls is not a good
experiment.  If it changes nothing we learn nothing; if it changes something
unpredictably we have an unexplained diff.  We need to know what we are looking
at before we touch it.

The way to know, without the consumer binary
--------------------------------------------
A boolean field is almost never a single global flag.  It is a property of a
*widget in a context*, and the resource files encode that context: the object's
class, its position among its siblings, and the screen it lives on.  So the
default value of the flag, correlated with those, tells us what it is.

Concretely, three correlations are checkable here:

C1  CLASS.  Objects of the same class_id should share a schema, and if the flag
    is per-widget-type then one class is uniformly 1 and another uniformly 0.
    A class that is always 1 is an "always on" widget kind; always 0 is "always
    off".  A class that is mixed is the interesting one.

C2  SCREEN ROLE.  The filename says what the screen is.  viewVersionNumber is
    an information screen; viewDummyBlack is a placeholder; viewQuickNavi is a
    navigation overlay.  If the flag is "visible" or "enabled", its default
    should track whether the screen has content to show.  If the default is
    identical across all of those, it is probably not visibility.

C3  POSITION.  A flag that varies with sibling index is z-order or focus; one
    that is constant regardless of position is a type default.

And there is a fourth, stronger source of evidence sitting in the corpus already:

C4  THE ZERO-MINORITY SET.  599 of 6069 instances are 0.  Those are the
    exceptions, and exceptions are informative: if the 0 cases cluster on a
    handful of classes or a handful of screens, that identifies the flag's
    purpose far better than the 5470 majority.  "What is different about the
    minority?" is the question to answer.

That last one is the most likely to produce a real answer, and it is why the
boolean is worth keeping: 9.9% minority is enough signal to characterise.

What this deliberately does not do
----------------------------------
It does not propose an edit.  It produces a reading of the flag with its
supporting counts, and an explicit list of what would falsify it.  An inference
from 6069 correlated instances with a named alternative is worth something; an
unexplained diff on a boot cycle is worth nothing.
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
        if not base.startswith('view'):
            continue
        out[base] = t.extractfile(m).read()
    return out


def collect(d):
    """Every (sig, payload offset 0) instance of the boolean, with context."""
    rows = []
    for name, b in sorted(d.items()):
        p = S.parse_view(b)
        for si, s in enumerate(p['sections']):
            objs = s['objects']
            for oi, o in enumerate(objs):
                for pi, pr in enumerate(o['props']):
                    if pr['sig'] != SIG or pr['payload_len'] != 1:
                        continue
                    v = b[pr['payload_off']]
                    rows.append(dict(
                        file=name, sec=si, obj=oi, prop=pi,
                        cls=o['class_id'], oid=o['object_id'],
                        parent=o['parent_id'], flags=o['flags'],
                        nprops=o['property_count'],
                        sibs=len(objs), value=v,
                        # where in the property list it sits
                        slot=pi,
                    ))
    return rows


def c1_class(rows):
    print('=' * 78)
    print('C1  by class: is the flag a per-widget-type default?')
    print('=' * 78)
    byc = defaultdict(Counter)
    for r in rows:
        byc[r['cls']][r['value']] += 1
    print()
    print('  %-10s %6s %6s %6s  %s' % ('class', 'ones', 'zeros', 'total', 'verdict'))
    verdicts = []
    for cls, c in sorted(byc.items(), key=lambda kv: -(kv[1][1] + kv[1][0])):
        n1, n0 = c[1], c[0]
        tot = n1 + n0
        if n0 == 0:
            v = 'ALWAYS 1'
        elif n1 == 0:
            v = 'ALWAYS 0'
        else:
            v = 'mixed %d/%d' % (n1, n0)
        verdicts.append((tot, cls, n1, n0, v))
    for tot, cls, n1, n0, v in verdicts[:20]:
        print('  %08x %6d %6d %6d  %s' % (cls, n1, n0, tot, v))
    print()
    print('  %d distinct classes carry this property' % len(verdicts))
    always1 = [v for v in verdicts if v[4] == 'ALWAYS 1']
    always0 = [v for v in verdicts if v[4] == 'ALWAYS 0']
    mixed = [v for v in verdicts if v[3] > 0 and v[2] > 0]
    print('    always 1 : %d classes' % len(always1))
    print('    always 0 : %d classes' % len(always0))
    print('    mixed    : %d classes' % len(mixed))
    return byc


def c4_minority(rows, byc):
    print()
    print('=' * 78)
    print('C4  the minority: what is different about the 599 zero cases?')
    print('=' * 78)
    zeros = [r for r in rows if r['value'] == 0]
    ones = [r for r in rows if r['value'] == 1]
    print()
    print('  ones %d   zeros %d' % (len(ones), len(zeros)))
    print()
    print('  --- by class (top 12 by zero count) ---')
    zc = Counter(r['cls'] for r in zeros)
    for cls, n in zc.most_common(12):
        tot = sum(byc[cls].values())
        print('    %08x  %4d zeros / %4d total  (%.0f%%)' % (cls, n, tot, 100.0 * n / tot))
    print()
    print('  --- by screen (top 16 by zero count) ---')
    zf = Counter(r['file'] for r in zeros)
    for f, n in zf.most_common(16):
        tot = sum(1 for r in rows if r['file'] == f)
        print('    %-42s %4d / %4d  (%.0f%%)' % (f[:42], n, tot, 100.0 * n / tot))
    print()
    print('  --- by object property_count ---')
    zp = Counter(r['nprops'] for r in zeros)
    op = Counter(r['nprops'] for r in ones)
    for np in sorted(set(zp) | set(op)):
        print('    %3d props: %4d zeros / %4d ones  (%.0f%% zero)'
              % (np, zp[np], op[np], 100.0 * zp[np] / max(1, zp[np] + op[np])))
    print()
    print('  --- by object flags byte ---')
    zf2 = Counter(r['flags'] for r in zeros)
    of2 = Counter(r['flags'] for r in ones)
    for f in sorted(set(zf2) | set(of2)):
        print('    flags=%d: %4d zeros / %4d ones' % (f, zf2[f], of2[f]))
    print()
    print('  --- by parent_id present ---')
    zp2 = sum(1 for r in zeros if r['parent'])
    op2 = sum(1 for r in ones if r['parent'])
    print('    with parent : %4d zeros / %4d ones' % (zp2, op2))
    print('    no parent   : %4d zeros / %4d ones'
          % (len(zeros) - zp2, len(ones) - op2))
    print()
    print('  --- by property slot index within the object ---')
    zs = Counter(r['slot'] for r in zeros)
    os_ = Counter(r['slot'] for r in ones)
    for s in sorted(set(zs) | set(os_))[:12]:
        print('    slot %2d: %4d zeros / %4d ones' % (s, zs[s], os_[s]))


def c2_screen_roles(rows):
    print()
    print('=' * 78)
    print('C2  by screen role: does the default track "has content"?')
    print('=' * 78)
    groups = {
        'placeholder/blank': ['viewDummyBlack', 'viewBaseMenu', 'viewNoImage'],
        'information': ['viewVersionNumber', 'viewCopyrightInformation',
                        'viewShootingInfoDisp', 'viewCaution'],
        'navigation/menu': ['viewGlobalMenu', 'viewQuickNavi', 'viewFnMenu',
                            'viewSettingMenu', 'viewModeButton'],
        'setting': ['viewWhiteBalance', 'viewFocusMode', 'viewFormat',
                    'viewRating', 'viewVolume', 'viewFocusArea'],
    }
    for role, pref in groups.items():
        tot = z = 0
        for r in rows:
            if any(r['file'].startswith(p) for p in pref):
                tot += 1
                z += (r['value'] == 0)
        if tot:
            print('  %-20s %5d instances, %4d zero (%.1f%%)'
                  % (role, tot, z, 100.0 * z / tot))
    print()
    print('  If one role is systematically more zero than the others, the flag')
    print('  is plausibly "this widget has something to show".  If every role')
    print('  sits at the same rate, it is not visibility.')


def c3_sibling_position(rows):
    print()
    print('=' * 78)
    print('C3  does it vary with position among siblings?')
    print('=' * 78)
    first = [r for r in rows if r['obj'] == 0]
    later = [r for r in rows if r['obj'] > 0]
    zf = sum(1 for r in first if r['value'] == 0)
    zl = sum(1 for r in later if r['value'] == 0)
    print('  first object in section: %4d instances, %4d zero (%.1f%%)'
          % (len(first), zf, 100.0 * zf / max(1, len(first))))
    print('  later objects          : %4d instances, %4d zero (%.1f%%)'
          % (len(later), zl, 100.0 * zl / max(1, len(later))))
    print()
    print('  A flag that varies with position is z-order or focus.  One that')
    print('  does not is a type default.')


def main():
    d = load()
    rows = collect(d)
    print('=== %d instances of %s across %d files ==='
          % (len(rows), SIG, len(set(r['file'] for r in rows))))
    print()
    byc = c1_class(rows)
    c2_screen_roles(rows)
    c3_sibling_position(rows)
    c4_minority(rows, byc)


if __name__ == '__main__':
    main()
