"""Classify the icon font's glyphs as text labels or shapes, and validate the test.

The question
------------
"Change all of them" is the right instinct, but only if "them" means the text
labels.  Plenty of glyphs in this font are shapes -- mode dials, the play and
pause transport icons, the warning triangle, the key -- and replacing a triangle
with letters would simply look broken, in the most prominent part of the UI.

So the set has to be found rather than assumed.  Surveying 1,684 glyphs by eye is
18 contact sheets, which is a lot of context and a lot of chances to skim.  A
measured classifier is better, provided it is validated.

The signal
----------
A text label is several separate letters standing on a common baseline and
reaching a common cap height.  So for each glyph:

  * split its contours into connected components by bounding-box overlap;
  * require at least two components, so a single blob is never called text;
  * require every component's yMin to sit within a small fraction of the
    glyph's yMin, and likewise yMax -- this is the baseline/cap-height test and
    is what a shape fails, because a triangle's parts do not share an extent;
  * require each component to be a decent fraction of the glyph height, so
    stray dots and accents do not count as letters;
  * require the glyph to be wider than it is tall, which text labels are and
    icons generally are not.

Why this can be trusted, and where it cannot
--------------------------------------------
It is validated against glyphs whose identity is already known by eye: seven
text labels seen in the first contact sheet (BRK, STD, FINE, HOLD, PAL, NTSC,
AUTO) must pass, and eight shapes from the same sheet (the transport icons, the
warning triangle, a dial) must fail.  A detector that does not separate those
two known sets has no standing on the other 1,669.

That is a real test with a real failure mode, and it is the reason this is worth
doing rather than just paging through screenshots.  It is still a heuristic on
the residue, and the residue is listed so it can be spot-checked rather than
trusted blindly.
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen

FONT = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share\app\Sony_DI_Icons.ttf')

# identified by eye in iconsheet_A (0xE000..0xE05F)
KNOWN_TEXT = {0xE053: 'BRK', 0xE054: 'STD', 0xE055: 'FINE', 0xE02D: 'HOLD',
              0xE059: 'PAL', 0xE05A: 'NTSC', 0xE05D: 'AUTO'}
KNOWN_SHAPE = {
    0xE000: 'mode dial', 0xE005: 'top plate', 0xE00A: 'dial marker',
    0xE010: 'warning triangle', 0xE016: 'infinity/mode', 0xE02A: 'wifi arcs',
    0xE035: 'key', 0xE037: 'face detect smiley', 0xE043: 'play/transport',
    0xE049: 'play+pause',
}


def components(glyph, gs, name):
    """group contours into connected components by bbox overlap"""
    pen = RecordingPen()
    gs[name].draw(pen)
    boxes = []
    cur = []
    for op, args in pen.value:
        if op == 'moveTo':
            if cur:
                boxes.append(cur)
            cur = [args[0]]
        else:
            for a in args:
                if isinstance(a, tuple):
                    cur.append(a)
    if cur:
        boxes.append(cur)
    comps = []
    for pts in boxes:
        if not pts:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        comps.append([min(xs), min(ys), max(xs), max(ys)])
    # merge overlapping boxes
    merged = True
    while merged:
        merged = False
        for i in range(len(comps)):
            for j in range(i + 1, len(comps)):
                a, b = comps[i], comps[j]
                if a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]:
                    comps[i] = [min(a[0], b[0]), min(a[1], b[1]),
                               max(a[2], b[2]), max(a[3], b[3])]
                    comps.pop(j)
                    merged = True
                    break
            if merged:
                break
    return comps, len(boxes)


def classify(comps, ncontours, bbox, min_comp_frac=0.35, align=0.18):
    x0, y0, x1, y1 = bbox
    h = y1 - y0
    w = x1 - x0
    if h <= 0 or w <= 0:
        return False, 'degenerate'
    if len(comps) < 2:
        return False, 'single component'
    tall = [c for c in comps
            if (c[3] - c[1]) >= min_comp_frac * h and (c[2] - c[0]) >= 1]
    if len(tall) < 2:
        return False, 'no letter-sized components'
    ys0 = [c[1] for c in tall]
    ys1 = [c[3] for c in tall]
    base_spread = (max(ys0) - min(ys0)) / float(h)
    cap_spread = (max(ys1) - min(ys1)) / float(h)
    if base_spread > align:
        return False, 'baselines differ (%.2f)' % base_spread
    if cap_spread > align:
        return False, 'cap heights differ (%.2f)' % cap_spread
    if w <= h * 1.05:
        return False, 'not wider than tall'
    return True, '%d letters, baseline spread %.2f' % (len(tall), base_spread)


def main():
    f = TTFont(FONT)
    f.ensureDecompiled()
    gs = f.getGlyphSet()
    glyf = f['glyf']
    cmap = f.getBestCmap()

    res = {}
    for cp, name in sorted(cmap.items()):
        if cp < 0xE000:
            continue
        g = glyf[name]
        if g.numberOfContours <= 0:
            continue
        try:
            g.recalcBounds(glyf)
        except Exception:
            continue
        bbox = (g.xMin, g.yMin, g.xMax, g.yMax)
        comps, ncont = components(g, gs, name)
        ok, why = classify(comps, ncont, bbox)
        res[cp] = (ok, why, len(comps), bbox)

    print('=== validation against glyphs already identified by eye ===')
    print()
    print('  must PASS (text labels):')
    bad = 0
    for cp, lbl in sorted(KNOWN_TEXT.items()):
        ok, why, nc, _ = res.get(cp, (False, 'missing', 0, None))
        flag = 'ok ' if ok else 'FAIL'
        if not ok:
            bad += 1
        print('    %s U+%04X  %-4s  %s' % (flag, cp, lbl, why))
    print()
    print('  must FAIL (shapes):')
    for cp, lbl in sorted(KNOWN_SHAPE.items()):
        ok, why, nc, _ = res.get(cp, (False, 'missing', 0, None))
        flag = 'ok ' if not ok else 'LEAK'
        if ok:
            bad += 1
        print('    %s U+%04X  %-18s %s' % (flag, cp, lbl, why))
    print()
    print('  validation errors: %d' % bad)
    print()

    texts = [cp for cp, (ok, _w, _n, _b) in res.items() if ok]
    shapes = [cp for cp, (ok, _w, _n, _b) in res.items() if not ok]
    print('=== the classification over all %d private-use glyphs ===' % len(res))
    print('  text labels : %d' % len(texts))
    print('  shapes      : %d' % len(shapes))
    print()
    why = Counter(w.split(' (')[0] for cp, (ok, w, _n, _b) in res.items() if not ok)
    print('  why the shapes were rejected:')
    for k, v in why.most_common():
        print('    %-28s %d' % (k, v))
    print()
    runs = []
    s = texts[0] if texts else 0
    p = s
    for cp in texts[1:]:
        if cp == p + 1:
            p = cp
        else:
            runs.append((s, p))
            s = cp
            p = cp
    if texts:
        runs.append((s, p))
    print('  the text labels are not scattered at random; they cluster:')
    for a, b in runs:
        n = sum(1 for cp in texts if a <= cp <= b)
        print('    U+%04X..U+%04X   %d glyphs' % (a, b, n))
    print()
    print('  every candidate, so the set can be inspected rather than trusted:')
    for i in range(0, len(texts), 12):
        row = texts[i:i + 12]
        print('    ' + '  '.join('U+%04X' % c for c in row))
    print()
    print('  aspect ratios of the candidates (w/h):')
    ars = sorted((res[c][3][2] - res[c][3][0]) / float(res[c][3][3] - res[c][3][1])
                 for c in texts)
    print('    min %.2f  median %.2f  max %.2f' % (ars[0], ars[len(ars) // 2], ars[-1]))


if __name__ == '__main__':
    main()
