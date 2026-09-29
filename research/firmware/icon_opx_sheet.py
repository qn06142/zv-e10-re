"""Render the 48 rewritten labels, original above and patched below.

The point of this sheet is to be looked at.  Every check so far has been
arithmetic -- contour counts, bounding boxes, advance widths, the int16 range --
and all of it can pass while the glyphs come out as overlapping mush, mirrored,
or with the letters stacked in one cell.  That is not hypothetical: an earlier
version of the stroke layout recomputed the pen origin inside the character loop
and drew every letter on top of the last, which produced a word narrower than a
shorter word and would have passed any check that did not render it.

The two rows are drawn at the same scale and the same cell so that a label which
has drifted taller than its original is visible as drift rather than as a
number in a log.  The rules are drawn in a different colour to the marker text
so it is obvious at a glance that Sony's frames survived and only the lettering
was replaced.
"""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen

sys.path.insert(0, str(Path(__file__).parent))
import icon_bars as ib
import icon_opx as op
import icon_targets_verified as tv

OUT = Path(r'C:\Users\qn061\AppData\Local\Temp\opencode\app_res')
ORIG = ib.FONT
PATCHED = OUT / 'Sony_DI_Icons.OPX.ttf'
CELL = 190
PER = 48


def cells(path, cps):
    f = TTFont(path)
    f.ensureDecompiled()
    gs = f.getGlyphSet()
    glyf = f['glyf']
    cmap = f.getBestCmap()
    out = []
    for cp in cps:
        nm = cmap[cp]
        p = SVGPathPen(gs)
        gs[nm].draw(p)
        g = glyf[nm]
        g.recalcBounds(glyf)
        out.append((cp, p.getCommands(), (g.xMin, g.yMin, g.xMax, g.yMax)))
    return out

def page(cps, pg, pages, top, bot):
    cols = 6
    parts = ['<!doctype html><meta charset="utf-8"><style>'
             'body{background:#141414;color:#ddd;font:12px monospace;margin:0}'
             'h2{background:#000;padding:9px 14px;margin:0;font:14px monospace}'
             '.g{display:grid;grid-template-columns:repeat(%d,%dpx);gap:6px;padding:10px}'
             '.c{background:#242424;border:1px solid #4a4a4a;padding:4px}'
             '.f{height:%dpx;position:relative;background:#1d3557}'
             '.f svg{position:absolute;left:0;top:0}'
             '.cp{color:#ffd479;font-size:11px;margin-top:2px}'
             '.ol{color:#cfd8dc;font-size:10px}.nw{color:#8bc34a;font-size:10px}'
             '</style>' % (cols, CELL + 8, CELL),
             '<h2>page %d of %d &mdash; original (white) above, patched (green) '
             'below. Check that the patched row really is this codepoint.</h2>'
             % (pg, pages)]
    for rowname, row, cls in (('original', top, 'ol'), ('patched', bot, 'nw')):
        parts.append('<h2 style="font-size:12px;padding:6px 14px">%s</h2><div class="g">'
                     % rowname)
        for cp, d, bb in row:
            x0, y0, x1, y1 = bb
            w = max(1, x1 - x0)
            h = max(1, y1 - y0)
            s = min(CELL * 0.88 / w, CELL * 0.88 / h)
            tx = (CELL - w * s) / 2 - x0 * s
            ty = (CELL - h * s) / 2 + y1 * s
            col = '#cfd8dc' if rowname == 'original' else '#8bc34a'
            parts.append('<div class="c"><div class="f"><svg width="%d" height="%d">'
                         '<g transform="translate(%.2f,%.2f) scale(%.5f,%.5f)">'
                         '<path d="%s" fill="%s"/></g></svg></div>'
                         '<div class="cp">U+%04X</div>'
                         '<div class="%s">%s</div></div>'
                         % (CELL, CELL, tx, ty, s, -s, d, col, cp, cls,
                            tv.TARGETS[cp]))
        parts.append('</div>')
    return parts


def main():
    allcps = sorted(tv.TARGETS)
    pages = (len(allcps) + PER - 1) // PER
    for pg in range(pages):
        cps = allcps[pg * PER:(pg + 1) * PER]
        o = OUT / ('opx_sheet_%d.html' % (pg + 1))
        o.write_text('\n'.join(page(cps, pg + 1, pages, cells(ORIG, cps),
                                    cells(PATCHED, cps))), encoding='utf-8')
        print('  %s  U+%04X..U+%04X' % (o, cps[0], cps[-1]))


if __name__ == '__main__':
    main()
