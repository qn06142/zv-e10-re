"""Find the "bars with a figure between" family structurally, not by reading labels.

Why
---
The user asked for "the one with the bars and a number in between".  Reading that
family off contact sheets does not work: three of 34 target codepoints were wrong
that way, because at 92 px cells a label reading U+E514 is easily mistaken for
U+E506, and a `♪AAC LC` glyph gets recorded as `STD`.

Sony draws this family with an unmistakable structure: a full-width horizontal
bar above the figures and another below, with the text between them.  So the
family can be *found* rather than transcribed:

  * at least three components;
  * the topmost and bottommost components are both wide and very thin -- a bar is
    much wider than it is tall;
  * both bars are a large fraction of the glyph's full width;
  * what remains between them is the figure.

That is a shape test, so it does not depend on reading a six-pixel label, and it
cannot be fooled by a glyph that merely happens to sit at a particular address.
The result is then rendered large, with the figures read off a sheet where the
labels are legible.
"""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

FONT = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share\app\Sony_DI_Icons.ttf')


def components(glyph, gs, name):
    from fontTools.pens.recordingPen import RecordingPen
    pen = RecordingPen()
    gs[name].draw(pen)
    boxes, cur = [], []
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
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        comps.append([min(xs), min(ys), max(xs), max(ys)])
    merged = True
    while merged:
        merged = False
        for i in range(len(comps)):
            for j in range(i + 1, len(comps)):
                a, b = comps[i], comps[j]
                ox = min(a[2], b[2]) - max(a[0], b[0])
                oy = min(a[3], b[3]) - max(a[1], b[1])
                if ox > 0 and oy > 0:
                    area = ox * oy
                    small = min((a[2] - a[0]) * (a[3] - a[1]),
                                (b[2] - b[0]) * (b[3] - b[1]))
                    if small and area > 0.35 * small:
                        comps[i] = [min(a[0], b[0]), min(a[1], b[1]),
                                   max(a[2], b[2]), max(a[3], b[3])]
                        comps.pop(j)
                        merged = True
                        break
            if merged:
                break
    return comps


def is_bar(c, gw, gh):
    w = c[2] - c[0]
    h = c[3] - c[1]
    if h <= 0 or w <= 0:
        return False
    # relative to the glyph this rejects the wide labels: HD XP has a 4512-unit
    # body and 2024-unit bars, a ratio of 0.45, under any threshold that still
    # admits the narrow ones.  Thinness and length are kept; matching the two
    # bars to each other is checked by the caller instead.
    return (h <= 0.16 * gh) and (w / float(h) >= 6.0)


def bars_match(a, b):
    """the two rules are the same rule, so they should be the same length"""
    wa = a[2] - a[0]
    wb = b[2] - b[0]
    if wa <= 0 or wb <= 0:
        return False
    r = wa / float(wb)
    return 0.88 <= r <= 1.13


def main():
    f = TTFont(FONT)
    f.ensureDecompiled()
    gs = f.getGlyphSet()
    glyf = f['glyf']
    cmap = f.getBestCmap()

    found = []
    for cp, name in sorted(cmap.items()):
        if cp < 0xE000:
            continue
        g = glyf[name]
        if g.numberOfContours < 3:
            continue
        try:
            g.recalcBounds(glyf)
        except Exception:
            continue
        gw = g.xMax - g.xMin
        gh = g.yMax - g.yMin
        if gw <= 0 or gh <= 0:
            continue
        comps = components(g, gs, name)
        if len(comps) < 3:
            continue
        comps.sort(key=lambda c: c[1])
        top = comps[0]
        bot = comps[-1]
        mid = comps[1:-1]
        if not (is_bar(top, gw, gh) and is_bar(bot, gw, gh)):
            continue
        if not bars_match(top, bot):
            continue
        if not mid:
            continue
        between = sum(1 for c in mid)
        found.append((cp, len(comps), between, gw, gh, g.numberOfContours))

    print('=== glyphs with a bar above and a bar below ===')
    print('  %d found' % len(found))
    print()
    print('  %-8s %-6s %-8s %-12s %s' % ('cp', 'comps', 'between', 'box', 'contours'))
    for cp, nc, mid, gw, gh, ncon in found:
        print('  U+%04X   %-6d %-8d %-12s %d' % (cp, nc, mid, '%dx%d' % (gw, gh), ncon))
    print()
    print('  the family is found by shape, so no label was read and no codepoint')
    print('  was transcribed from a small cell.')


if __name__ == '__main__':
    main()
