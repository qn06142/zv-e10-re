"""Render the bar family large, to read the figures and catch false positives.

icon_bars.py finds the family by shape, which is sound in principle, but a shape
test has no opinion about what it found.  Loosening the width test from 0.55 of
the glyph to "the two bars match each other" took the count from 19 to 28 and
picked up four more genuinely barred labels -- HD SP, HD LP, HD HQ and a fourth
-- which the old test was rejecting for being wide.  That is the change working.

It also picked up three suspects that may be coincidence: U+E247..U+E249 are
5268 units wide with 17 contours each, and U+E609 is nearly square at 1739x1742,
so neither reads as "a short figure between two rules" without looking.

So the detector produces a shortlist and this renders it at a size where the
figures can actually be read, which is the only way to tell a barred label from a
shape that merely happens to have a thin component top and bottom.
"""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen

sys.path.insert(0, str(Path(__file__).parent))
import icon_bars as ib

OUT = Path(r'C:\Users\qn061\AppData\Local\Temp\opencode\app_res')
FONT = ib.FONT


def find():
    f = TTFont(FONT)
    f.ensureDecompiled()
    gs = f.getGlyphSet()
    glyf = f['glyf']
    out = []
    for cp, name in sorted(f.getBestCmap().items()):
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
        comps = ib.components(g, gs, name)
        if len(comps) < 3:
            continue
        comps.sort(key=lambda c: c[1])
        top, bot = comps[0], comps[-1]
        if not (ib.is_bar(top, gw, gh) and ib.is_bar(bot, gw, gh)):
            continue
        if not ib.bars_match(top, bot):
            continue
        if not comps[1:-1]:
            continue
        out.append(cp)
    return f, out


def main():
    f, cands = find()
    gs = f.getGlyphSet()
    glyf = f['glyf']
    cmap = f.getBestCmap()
    print('bar family: %d glyphs' % len(cands))

    cell = 260
    cols = 5
    rows = (len(cands) + cols - 1) // cols
    parts = ['<!doctype html><meta charset="utf-8"><style>'
             'body{background:#181818;color:#ddd;font:13px monospace}'
             'h2{background:#0a0a0a;padding:10px 14px;margin:0;font:14px monospace}'
             '.g{display:grid;grid-template-columns:repeat(%d,%dpx);gap:12px;padding:14px}'
             '.c{background:#2b2b2b;border:1px solid #666;padding:8px}'
             '.f{height:%dpx;position:relative}.f svg{position:absolute;left:0;top:0}'
             '.cp{color:#ffd479;font-size:15px;font-weight:bold;margin-top:4px}'
             '.m{color:#7f7f7f;font-size:11px}</style>'
             % (cols, cell + 16, cell),
             '<h2>bar family &mdash; %d found by shape; read each figure, and '
             'flag anything that is not a figure between two rules</h2>'
             '<div class="g">' % len(cands)]
    for cp in cands:
        nm = cmap[cp]
        p = SVGPathPen(gs)
        gs[nm].draw(p)
        d = p.getCommands()
        g = glyf[nm]
        x0, y0, x1, y1 = g.xMin, g.yMin, g.xMax, g.yMax
        w = max(1, x1 - x0)
        h = max(1, y1 - y0)
        s = min(cell * 0.9 / w, cell * 0.9 / h)
        tx = (cell - w * s) / 2 - x0 * s
        ty = (cell - h * s) / 2 + y1 * s
        parts.append('<div class="c"><div class="f"><svg width="%d" height="%d">'
                     '<g transform="translate(%.2f,%.2f) scale(%.5f,%.5f)">'
                     '<path d="%s" fill="#fff"/></g></svg></div>'
                     '<div class="cp">U+%04X</div>'
                     '<div class="m">%d x %d, %d contours</div></div>'
                     % (cell, cell, tx, ty, s, -s, d, cp, w, h, g.numberOfContours))
    parts.append('</div>')
    o = OUT / 'bar_family.html'
    o.write_text('\n'.join(parts), encoding='utf-8')
    print('wrote %s' % o)


if __name__ == '__main__':
    main()
