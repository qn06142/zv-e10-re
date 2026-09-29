"""Find the resolution labels by their slash, and read the whole family.

Why
---
U+E558 was recorded as "2160/30p" and turned out to be a landscape-and-arrows
pictogram.  So the resolution list, like the bar list, has to be established by
something other than transcribing small contact-sheet labels.

The signature is the slash.  Every one of these reads as digits, a slash, more
digits, then a trailing p or i, and the slash is the only component in the glyph
that is much taller than it is wide.  Looking for that finds candidates without
reading anything, and the same way as the bar family the result is then rendered
large enough to read, because a shape test has no opinion about what it matched.

The trailing unit matters too: 1080/60p and 1080/50p differ only in the last
two characters, and a panel that is fixed-width will draw both, so the family is
reported with its advance width to show which ones the UI sizes identically.
"""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen

sys.path.insert(0, str(Path(__file__).parent))
import icon_bars as ib

OUT = Path(r'C:\Users\qn061\AppData\Local\Temp\opencode\app_res')
FONT = ib.FONT


def has_slash(comps, gh):
    """a component far taller than wide, standing well up and down the glyph"""
    for c in comps:
        w = c[2] - c[0]
        h = c[3] - c[1]
        if h <= 0 or w <= 0:
            continue
        if h >= 2.5 * w and h >= 0.55 * gh:
            return True
    return False


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
        if g.numberOfContours < 6:
            continue
        try:
            g.recalcBounds(glyf)
        except Exception:
            continue
        gw = g.xMax - g.xMin
        gh = g.yMax - g.yMin
        if gw <= 0 or gh <= 0 or gw < 2.0 * gh:
            continue
        comps = ib.components(g, gs, name)
        if len(comps) < 4:
            continue
        if has_slash(comps, gh):
            out.append(cp)
    return f, out


def main():
    f, cands = find()
    gs = f.getGlyphSet()
    glyf = f['glyf']
    cmap = f.getBestCmap()
    hmtx = f['hmtx']
    print('slash-bearing candidates: %d' % len(cands))

    cell = 250
    cols = 5
    parts = ['<!doctype html><meta charset="utf-8"><style>'
             'body{background:#181818;color:#ddd;font:13px monospace}'
             'h2{background:#0a0a0a;padding:10px 14px;margin:0;font:14px monospace}'
             '.g{display:grid;grid-template-columns:repeat(%d,%dpx);gap:12px;padding:14px}'
             '.c{background:#2b2b2b;border:1px solid #666;padding:8px}'
             '.f{height:%dpx;position:relative}.f svg{position:absolute;left:0;top:0}'
             '.cp{color:#ffd479;font-size:15px;font-weight:bold;margin-top:4px}'
             '.m{color:#7f7f7f;font-size:11px}</style>'
             % (cols, cell + 16, cell),
             '<h2>resolution family &mdash; %d glyphs containing a slash; '
             'read each, discard anything that is not a frame rate</h2>'
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
        s = min(cell * 0.92 / w, cell * 0.92 / h)
        tx = (cell - w * s) / 2 - x0 * s
        ty = (cell - h * s) / 2 + y1 * s
        parts.append('<div class="c"><div class="f"><svg width="%d" height="%d">'
                     '<g transform="translate(%.2f,%.2f) scale(%.5f,%.5f)">'
                     '<path d="%s" fill="#fff"/></g></svg></div>'
                     '<div class="cp">U+%04X</div>'
                     '<div class="m">adv %d, %d x %d</div></div>'
                     % (cell, cell, tx, ty, s, -s, d, cp, hmtx[nm][0], w, h))
    parts.append('</div>')
    o = OUT / 'res_family.html'
    o.write_text('\n'.join(parts), encoding='utf-8')
    print('wrote %s' % o)


if __name__ == '__main__':
    main()
