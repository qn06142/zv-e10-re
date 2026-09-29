"""Check the patch at the size the camera actually draws it, and zoom the fiddly bits.

A contact sheet at 190 px is flattering.  These labels are drawn on a 640x480
screen somewhere around 60 to 100 units tall, where a stroke font with heavy
rectangles can turn into an unreadable grey smear -- and that is the only size
that matters.  So this renders each label three ways:

  large    520 px, to inspect the construction
  real     84 px, roughly what the camera puts on screen
  tiny     44 px, the worst case

and it zooms the four labels whose construction was least certain: the colon in
16:9, which could merge into a single dash, the plus in HQ+, the X, and the
filmstrip composite STD HQ, where the decision to keep only the outer rules means
the filmstrip frame itself is not preserved.
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
PATCHED = OUT / 'Sony_DI_Icons.OPX.ttf'
ORIG = ib.FONT

ZOOM = [0xE041, 0xE103, 0xE540, 0xE247]
SAMPLE = [0xE03E, 0xE041, 0xE1F9, 0xE1FD, 0xE21C, 0xE536, 0xE505, 0xE52B]


def path_of(path, cp):
    f = TTFont(path)
    f.ensureDecompiled()
    gs = f.getGlyphSet()
    g = f['glyf'][f.getBestCmap()[cp]]
    g.recalcBounds(f['glyf'])
    p = SVGPathPen(gs)
    gs[cp if False else f.getBestCmap()[cp]].draw(p)
    return p.getCommands(), (g.xMin, g.yMin, g.xMax, g.yMax)


def svg(d, bb, size, col):
    x0, y0, x1, y1 = bb
    w = max(1, x1 - x0)
    h = max(1, y1 - y0)
    s = min(size * 0.9 / w, size * 0.9 / h)
    tx = (size - w * s) / 2 - x0 * s
    ty = (size - h * s) / 2 + y1 * s
    return ('<svg width="%d" height="%d"><g transform="translate(%.2f,%.2f) '
            'scale(%.5f,%.5f)"><path d="%s" fill="%s"/></g></svg>'
            % (size, size, tx, ty, s, -s, d, col))


def main():
    p = ['<!doctype html><meta charset="utf-8"><style>'
         'body{background:#141414;color:#ddd;font:12px monospace}'
         'h2{background:#000;padding:9px 14px;margin:0;font:14px monospace}'
         'h3{color:#8bc34a;font:12px monospace;padding:8px 14px 0;margin:0}'
         'table{border-collapse:collapse}td{padding:3px;text-align:center;'
         'vertical-align:bottom}svg{background:#1d3557;display:block}'
         '.l{color:#ffd479;font-size:10px}.o{color:#cfd8dc;font-size:10px}'
         '</style>']

    p.append('<h2>zoom: the four labels whose construction was least certain'
             '</h2><table><tr><th></th>')
    for cp in ZOOM:
        p.append('<th>U+%04X<br><span class="o">%s</span></th>' % (cp, tv.TARGETS[cp]))
    p.append('</tr>')
    for label, path, col, cls in (('original', ORIG, '#cfd8dc', 'o'),
                                  ('patched', PATCHED, '#8bc34a', 'l')):
        p.append('<tr><th class="%s">%s</th>' % (cls, label))
        for cp in ZOOM:
            d, bb = path_of(path, cp)
            p.append('<td>%s<div class="%s">%s</div></td>'
                     % (svg(d, bb, 300, col), cls, op.marker_string(tv.TARGETS[cp])))
        p.append('</tr>')
    p.append('</table>')

    for size, tag in ((520, 'large 520 px'), (84, 'real 84 px, about what the '
                                               'camera draws'), (44, 'tiny 44 px')):
        p.append('<h3>%s</h3><table><tr><th></th>' % tag)
        for cp in SAMPLE:
            p.append('<th>U+%04X</th>' % cp)
        p.append('</tr>')
        for label, path, col, cls in (('original', ORIG, '#cfd8dc', 'o'),
                                      ('patched', PATCHED, '#8bc34a', 'l')):
            p.append('<tr><th class="%s">%s</th>' % (cls, label))
            for cp in SAMPLE:
                d, bb = path_of(path, cp)
                p.append('<td>%s<div class="%s">%s</div></td>'
                         % (svg(d, bb, size, col), cls, tv.TARGETS[cp]))
            p.append('</tr>')
        p.append('</table>')

    o = OUT / 'opx_zoom.html'
    o.write_text('\n'.join(p), encoding='utf-8')
    print('wrote %s' % o)


if __name__ == '__main__':
    main()
