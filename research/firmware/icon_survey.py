"""Survey the remaining text labels, at a size where the codepoint is readable.

The lesson from the first target list
-------------------------------------
Three of thirty-four codepoints were wrong because they were read off 92-pixel
cells with 10-pixel labels: U+E514 was recorded as U+E506, and U+E5B3 as
U+E558.  Reading a six-character hex string off a thumbnail is not identification,
it is guessing with extra steps.  So this renders 60 to a page at 200-pixel cells
with 20-pixel labels, which is dull and slow and does not lie.

The candidate list comes from icon_classify, which proposes 211 text labels out
of 1,683 private-use glyphs.  That classifier is not trusted -- it misclassifies
the transport icons, whose two triangles share a baseline as neatly as two letters
do -- so it is used only to decide what is worth rendering.  What each glyph
actually is, is decided here by looking.
"""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen

sys.path.insert(0, str(Path(__file__).parent))
import icon_classify as ic
import icon_targets_verified as tv

OUT = Path(r'C:\Users\qn061\AppData\Local\Temp\opencode\app_res')
PER = 60
COLS = 10
CELL = 200


def candidates():
    f = TTFont(ic.FONT)
    f.ensureDecompiled()
    gs = f.getGlyphSet()
    glyf = f['glyf']
    out = []
    for cp, name in sorted(f.getBestCmap().items()):
        if cp < 0xE000 or cp in tv.TARGETS:
            continue
        g = glyf[name]
        if g.numberOfContours <= 0:
            continue
        try:
            g.recalcBounds(glyf)
        except Exception:
            continue
        comps, ncont = ic.components(g, gs, name)
        ok, _why = ic.classify(comps, ncont, (g.xMin, g.yMin, g.xMax, g.yMax))
        if ok:
            out.append(cp)
    return f, out


def main():
    f, cands = candidates()
    gs = f.getGlyphSet()
    glyf = f['glyf']
    cmap = f.getBestCmap()
    print('unexamined text-label candidates: %d' % len(cands))
    pages = (len(cands) + PER - 1) // PER
    for pg in range(pages):
        chunk = cands[pg * PER:(pg + 1) * PER]
        p = ['<!doctype html><meta charset="utf-8"><style>'
             'body{background:#181818;color:#ddd;font:20px monospace}'
             'h2{background:#000;padding:10px 14px;margin:0;font:18px monospace}'
             '.g{display:grid;grid-template-columns:repeat(%d,%dpx);gap:8px;padding:10px}'
             '.c{background:#2b2b2b;border:1px solid #555}'
             '.f{height:%dpx;position:relative;background:#1d3557}'
             '.f svg{position:absolute;left:0;top:0}'
             '.cp{color:#ffd479;font-size:20px;font-weight:bold;padding:4px 6px}'
             '</style>' % (COLS, CELL, CELL),
             '<h2>page %d of %d &mdash; transcribe the labels, do not guess '
             'them</h2><div class="g">' % (pg + 1, pages)]
        for cp in chunk:
            nm = cmap[cp]
            sp = SVGPathPen(gs)
            gs[nm].draw(sp)
            g = glyf[nm]
            x0, y0, x1, y1 = g.xMin, g.yMin, g.xMax, g.yMax
            w = max(1, x1 - x0)
            h = max(1, y1 - y0)
            s = min(CELL * 0.86 / w, CELL * 0.86 / h)
            tx = (CELL - w * s) / 2 - x0 * s
            ty = (CELL - h * s) / 2 + y1 * s
            p.append('<div class="c"><div class="f"><svg width="%d" height="%d">'
                     '<g transform="translate(%.2f,%.2f) scale(%.5f,%.5f)">'
                     '<path d="%s" fill="#fff"/></g></svg></div>'
                     '<div class="cp">U+%04X</div></div>'
                     % (CELL, CELL, tx, ty, s, -s, sp.getCommands(), cp))
        p.append('</div>')
        o = OUT / ('survey_%d.html' % (pg + 1))
        o.write_text('\n'.join(p), encoding='utf-8')
        print('  %s  (U+%04X..U+%04X)' % (o, chunk[0], chunk[-1]))


if __name__ == '__main__':
    main()
