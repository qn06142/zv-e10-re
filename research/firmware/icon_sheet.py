"""Render a labelled contact sheet of the icon font's private-use glyphs.

Why this is the right first step
--------------------------------
Sony_DI_Icons.ttf is a real TrueType font: 1,732 glyphs, 2048 units/em, long
loca, post format 2.0.  1,684 codepoints in the Unicode Private Use Area
(0xE000..0xEB29) are mapped, and the camera's UI draws its icons as glyphs from
this font.  The outlines are plain vectors with no colour, so the renderer
supplies the colour -- which means recolouring the font would do nothing, and
reshaping an outline would change the icon's shape.

But the glyph names are useless for identification: they are all `uniE8xx.001`
style, derived from the codepoint.  So the icons cannot be named from the font,
only recognised by looking at them.  Hence a contact sheet.

This is the step that makes the rest possible.  Without knowing which codepoint
is, say, the record dot or the battery, any edit is a shot in the dark, and a
shot in the dark on a 1,684-glyph font is exactly the kind of unquantified change
this project refuses to make.

Method
------
fontTools' SVGPathPen turns each glyph outline into SVG path data, which is
exact -- no rasteriser, no approximation, nothing invented.  The paths go into a
plain HTML grid with the codepoint under each cell.  Nothing is written to the
camera; this is a local artefact for looking at.
"""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen

FONT = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share\app\Sony_DI_Icons.ttf')
OUT = Path(r'C:\Users\qn061\AppData\Local\Temp\opencode\app_res')


def main():
    lo = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0xE000
    hi = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0xE0A7
    cols = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    tag = sys.argv[4] if len(sys.argv) > 4 else ('%04X' % lo)

    f = TTFont(FONT)
    upem = f['head'].unitsPerEm
    cmap = f.getBestCmap()
    gs = f.getGlyphSet()
    order = f.getGlyphOrder()
    index = {n: i for i, n in enumerate(order)}
    hmtx = f['hmtx']

    cells = []
    nempty = 0
    for cp in range(lo, hi + 1):
        name = cmap.get(cp)
        if name is None:
            nempty += 1
            cells.append((cp, None, None, 0, 0))
            continue
        pen = SVGPathPen(gs)
        gs[name].draw(pen)
        d = pen.getCommands()
        adv, lsb = hmtx[name]
        cells.append((cp, name, d, adv, f['glyf'][name].xMin if f['glyf'][name].numberOfContours else 0))

    cell = 96
    pad = 16
    label = 22
    rows = (len(cells) + cols - 1) // cols
    w = cols * (cell + pad) + pad
    h = rows * (cell + label + pad) + pad + 40

    parts = ['<!doctype html><meta charset="utf-8">',
             '<style>body{background:#202020;color:#e0e0e0;font:12px monospace;margin:0}',
             'h2{font:14px monospace;padding:10px 14px;margin:0;background:#101010}',
             '.g{display:grid;grid-template-columns:repeat(%d,%dpx);gap:%dpx;padding:%dpx}'
             % (cols, cell, pad, pad),
             '.c{background:#2a2a2a;border:1px solid #444;height:%dpx;position:relative}'
             % (cell + label),
             '.c svg{position:absolute;left:0;top:0}',
             '.l{position:absolute;bottom:2px;left:0;right:0;text-align:center;font-size:10px;color:#9a9a9a}',
             '.m{position:absolute;left:2px;top:1px;font-size:9px;color:#6a6a6a}</style>',
             '<h2>Sony_DI_Icons.ttf &mdash; private-use glyphs 0x%04X..0x%04X '
             '(%d mapped, %d unmapped in range) &mdash; %d glyphs total, %d upem</h2>'
             % (lo, hi, len(cells) - nempty, nempty, f['maxp'].numGlyphs, upem),
             '<div class="g">']

    for cp, name, d, adv, _x in cells:
        parts.append('<div class="c">')
        if d and name:
            g = f['glyf'][name]
            try:
                g.recalcBounds(f['glyf'])
                x0, y0, x1, y1 = g.xMin, g.yMin, g.xMax, g.yMax
            except Exception:
                x0, y0, x1, y1 = 0, 0, upem, upem
            w = max(1, x1 - x0)
            h = max(1, y1 - y0)
            # fit the glyph's own box into the cell, preserving aspect.  No
            # viewBox scaling on top: the first version had viewBox 0 0 2048 2048
            # *and* a 0.037 scale, so every icon rendered 27x too small.
            s = min(cell * 0.80 / w, cell * 0.80 / h)
            tx = (cell - w * s) / 2.0 - x0 * s
            ty = (cell + h * s) / 2.0 + y1 * s
            parts.append(
                '<svg width="%d" height="%d">'
                '<g transform="translate(%.2f,%.2f) scale(%.5f,%.5f)">'
                '<path d="%s" fill="#ffffff"/></g></svg>'
                % (cell, cell, tx, ty, s, -s, d))
        else:
            parts.append('<div style="position:absolute;left:%dpx;top:%dpx;color:#555">'
                         '&mdash;</div>' % (cell // 2 - 6, cell // 2 - 6))
        parts.append('<div class="m">%d</div>' % index.get(name, -1) if name else '')
        parts.append('<div class="l">U+%04X</div></div>' % cp)

    parts.append('</div>')
    out = OUT / ('iconsheet_%s.html' % tag)
    out.write_text('\n'.join(parts), encoding='utf-8')
    print('wrote %s' % out)
    print('  %d cells, %d mapped' % (len(cells), len(cells) - nempty))
    print('  open it in a browser to view')


if __name__ == '__main__':
    main()
