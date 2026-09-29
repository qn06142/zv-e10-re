"""Replace a glyph's outline in the icon font, and preview the result locally.

The target, and why it is the best one available
-------------------------------------------------
fontlist.dat registers six fonts, and the last line is

    FONT_ICONS   /usr/share/app/Sony_DI_Icons.ttf

so the icon font is that standalone 619 KB TrueType file, not one of the .ltt
bundles -- those are the *text* fonts, which link the icon font in for fallback.
The file is a documented standard format, it lives on a filesystem already proven
writable, and the camera draws its UI labels as glyphs from it.  Nothing about it
is proprietary and there is no key table, checksum or unknown addressing scheme --
which is the first target in this project where that is true.

What is being changed, and what is not
--------------------------------------
Only the *outline* of chosen glyphs.  Glyph count, cmap, metrics, advance widths
and every other table are left alone, so the font stays structurally identical
and the only visible effect is the shape of the icons named.

The font contains no Latin letters -- its cmap maps one codepoint below the
private use area, U+0020, and everything else is PUA.  So the letterforms inside
glyphs like "STD" are custom outlines, and a new word cannot be composed from
existing glyphs.  It has to be drawn.  Hence the small stroke font below: each
character is a set of line segments in a unit box, thickened into rectangles and
emitted as TrueType contours.  Crude, but it is honest vector geometry with no
dependency on anything in the font.

Nothing here writes to the camera.  It produces a preview and, on request, a
patched font plus its md5, for a separate deliberate flash step.
"""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
from fontTools.ttLib.tables.ttProgram import Program
from fontTools.pens.recordingPen import RecordingPen

FONT = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share\app\Sony_DI_Icons.ttf')
OUT = Path(r'C:\Users\qn061\AppData\Local\Temp\opencode\app_res')

# A stroke font: each character is a list of segments in a 0..1 x 0..1 box,
# (x0,y0,x1,y1).  y is 0 at the baseline and 1 at the cap height.  This is
# deliberately blocky -- the point is to be unmistakably not-Sony, not pretty.
STROKES = {
    'A': [(0, 0, 0, 1), (0, 1, 1, 1), (1, 1, 1, 0), (0, 0.5, 1, 0.5)],
    'B': [(0, 0, 0, 1), (0, 1, 0.8, 1), (0.8, 1, 0.8, 0.55), (0.8, 0.55, 0, 0.55),
          (0, 0.55, 0.9, 0.55), (0.9, 0.55, 0.9, 0), (0.9, 0, 0, 0)],
    'C': [(1, 0.8, 0.2, 1), (0.2, 1, 0, 0.6), (0, 0.6, 0, 0.4), (0, 0.4, 0.2, 0),
          (0.2, 0, 1, 0.2)],
    'D': [(0, 0, 0, 1), (0, 1, 0.6, 1), (0.6, 1, 1, 0.6), (1, 0.6, 1, 0.4),
          (1, 0.4, 0.6, 0), (0.6, 0, 0, 0)],
    'E': [(1, 1, 0, 1), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0.5, 0.8, 0.5)],
    'F': [(1, 1, 0, 1), (0, 1, 0, 0), (0, 0.5, 0.8, 0.5)],
    'G': [(1, 0.8, 0.2, 1), (0.2, 1, 0, 0.6), (0, 0.6, 0, 0.4), (0, 0.4, 0.2, 0),
          (0.2, 0, 1, 0.2), (1, 0.2, 1, 0.5), (1, 0.5, 0.5, 0.5)],
    'H': [(0, 0, 0, 1), (1, 0, 1, 1), (0, 0.5, 1, 0.5)],
    'I': [(0.5, 0, 0.5, 1), (0.1, 1, 0.9, 1), (0.1, 0, 0.9, 0)],
    'J': [(0.9, 1, 0.9, 0.2), (0.9, 0.2, 0.5, 0), (0.5, 0, 0.1, 0.2)],
    'K': [(0, 0, 0, 1), (0, 0.5, 0.9, 1), (0, 0.5, 0.9, 0)],
    'L': [(0, 1, 0, 0), (0, 0, 0.9, 0)],
    'M': [(0, 0, 0, 1), (0, 1, 0.5, 0.4), (0.5, 0.4, 1, 1), (1, 1, 1, 0)],
    'N': [(0, 0, 0, 1), (0, 1, 1, 0), (1, 0, 1, 1)],
    'O': [(0.2, 0, 0, 0.3), (0, 0.3, 0, 0.7), (0, 0.7, 0.2, 1), (0.2, 1, 0.8, 1),
          (0.8, 1, 1, 0.7), (1, 0.7, 1, 0.3), (1, 0.3, 0.8, 0)],
    'P': [(0, 0, 0, 1), (0, 1, 0.8, 1), (0.8, 1, 0.8, 0.5), (0.8, 0.5, 0, 0.5)],
    'Q': [(0.2, 0, 0, 0.3), (0, 0.3, 0, 0.7), (0, 0.7, 0.2, 1), (0.2, 1, 0.8, 1),
          (0.8, 1, 1, 0.7), (1, 0.7, 1, 0.3), (1, 0.3, 0.8, 0), (0.6, 0.3, 1.1, -0.2)],
    'R': [(0, 0, 0, 1), (0, 1, 0.8, 1), (0.8, 1, 0.8, 0.5), (0.8, 0.5, 0, 0.5),
          (0.4, 0.5, 1, 0)],
    'S': [(1, 0.85, 0.2, 1), (0.2, 1, 0, 0.75), (0, 0.75, 0.2, 0.55), (0.2, 0.55, 0.8, 0.45),
          (0.8, 0.45, 1, 0.25), (1, 0.25, 0.8, 0), (0.8, 0, 0, 0.15)],
    'T': [(0, 1, 1, 1), (0.5, 1, 0.5, 0)],
    'U': [(0, 1, 0, 0.2), (0, 0.2, 0.5, 0), (0.5, 0, 1, 0.2), (1, 0.2, 1, 1)],
    'V': [(0, 1, 0.5, 0), (0.5, 0, 1, 1)],
    'W': [(0, 1, 0.2, 0), (0.2, 0, 0.5, 0.6), (0.5, 0.6, 0.8, 0), (0.8, 0, 1, 1)],
    'X': [(0, 1, 1, 0), (0, 0, 1, 1)],
    'Y': [(0, 1, 0.5, 0.5), (1, 1, 0.5, 0.5), (0.5, 0.5, 0.5, 0)],
    'Z': [(0, 1, 1, 1), (1, 1, 0, 0), (0, 0, 1, 0)],
    '0': [(0.2, 0, 0, 0.3), (0, 0.3, 0, 0.7), (0, 0.7, 0.2, 1), (0.2, 1, 0.8, 1),
          (0.8, 1, 1, 0.7), (1, 0.7, 1, 0.3), (1, 0.3, 0.8, 0)],
    '1': [(0.2, 0.8, 0.5, 1), (0.5, 1, 0.5, 0), (0.2, 0, 0.8, 0)],
    '2': [(0, 0.8, 0.3, 1), (0.3, 1, 0.8, 1), (0.8, 1, 1, 0.7), (1, 0.7, 0, 0),
          (0, 0, 1, 0)],
    '5': [(1, 1, 0, 1), (0, 1, 0, 0.55), (0, 0.55, 0.7, 0.6), (0.7, 0.6, 1, 0.3),
          (1, 0.3, 0.7, 0), (0.7, 0, 0, 0.15)],
    '8': [(0.3, 0.55, 0, 0.75), (0, 0.75, 0.3, 1), (0.3, 1, 0.7, 1), (0.7, 1, 1, 0.75),
          (1, 0.75, 0.7, 0.55), (0.7, 0.55, 1, 0.3), (1, 0.3, 0.7, 0), (0.7, 0, 0, 0.25),
          (0, 0.25, 0.3, 0.55), (0.3, 0.55, 0.7, 0.55)],
    ' ': [],
    '.': [(0.4, 0, 0.6, 0), (0.4, 0.2, 0.6, 0.2)],
    '-': [(0.1, 0.5, 0.9, 0.5)],
    '!': [(0.5, 1, 0.5, 0.25), (0.5, 0, 0.5, 0.15)],
}


def thicken(x0, y0, x1, y1, w):
    """a segment as a rectangle contour (4 points, clockwise)"""
    dx, dy = x1 - x0, y1 - y0
    L = (dx * dx + dy * dy) ** 0.5
    if L == 0:
        return None
    nx, ny = -dy / L * w / 2.0, dx / L * w / 2.0
    return [(x0 + nx, y0 + ny), (x1 + nx, y1 + ny),
            (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)]


def build_glyph(font, text, width, height, weight, gap, name):
    """a Glyph whose outline is `text` drawn to fit width x height

    The glyph MUST keep the original's name.  The first version invented a name
    like '.gen_OPX', which is not in the font's glyph order; loca is then indexed
    by position while the new glyph is not in that order, and compiling glyf
    fails with "unpack requires a buffer of 10 bytes" deep inside sstruct.  The
    glyph order is part of the format's identity, so the name is not free.
    """
    g = Glyph(name)
    n = max(1, len(text))
    # fit the word into the given box
    cellw = width / float(n)
    sw = cellw - gap
    sh = height
    thick = weight * min(sw, sh) * 0.9
    pen = RecordingPen()
    pen.moveTo((0, 0))
    pen.lineTo((0, 0))
    pen.closePath()
    coords, endPts, flags = GlyphCoordinates([]), [], []
    # The pen origin is computed ONCE, before the character loop.  The first
    # version recomputed `ox = (cellw - sw) / 2` at the top of every iteration,
    # which overwrote the `ox += cellw` from the previous one, so every letter
    # was drawn stacked in the same cell: "OPX" produced x 143..794 inside an
    # original box 2812 wide, and "HACK" came out narrower than "OPX".  A word
    # with more letters was physically smaller, which is what gave it away.
    ox = (cellw - sw) / 2.0
    for ch in text:
        segs = STROKES.get(ch.upper())
        if not segs:
            continue
        # centre this character in its cell
        xs = [s[0] for s in segs] + [s[2] for s in segs]
        gw = (max(xs) - min(xs)) if xs else 0.0
        if gw <= 0:
            # a character drawn only with vertical strokes (or a stray entry):
            # fall back to its nominal cell width rather than dividing by zero
            gw = 1.0
        for (ax, ay, bx, by) in segs:
            r = thicken(ox + (ax - min(xs)) * sw / gw, ay * sh,
                        ox + (bx - min(xs)) * sw / gw, by * sh, thick)
            if not r:
                continue
            base = len(coords)
            for (px, py) in r:
                coords.append((int(round(px)), int(round(py))))
                flags.append(0)
            endPts.append(base + 3)
        ox += cellw
    if not endPts:
        return None
    g.coordinates = coords
    g.endPtsOfContours = endPts
    g.flags = array_of_flags(flags)
    g.program = Program()
    g.numberOfContours = len(endPts)
    return g


def array_of_flags(flags):
    from array import array
    return array('B', flags)


def apply_edits(edits, outpath):
    """edits: list of (codepoint, new_text, weight_fraction)"""
    f = TTFont(FONT)
    # Decompile every glyph before touching any of them.  fontTools loads glyf
    # lazily, so a table ends up holding a mix of raw byte blobs and expanded
    # objects; recompiling then walks the stale loca and dies with "unpack
    # requires a buffer of 10 bytes".  ensureDecompiled makes the table uniform,
    # which is a precondition for editing it at all.
    f.ensureDecompiled()
    cmap = f.getBestCmap()
    glyf = f['glyf']
    report = []
    for cp, text, wf in edits:
        name = cmap.get(cp)
        if name is None:
            report.append((cp, text, 'NO MAPPED GLYPH'))
            continue
        old = glyf[name]
        try:
            old.recalcBounds(glyf)
            w = old.xMax - old.xMin
            h = old.yMax - old.yMin
        except Exception:
            w = h = 0
        if w <= 8 or h <= 8:
            w, h = 1000, 700
        newg = build_glyph(f, text, w, h, wf, gap=w * 0.14, name=name)
        if newg is None or not newg.numberOfContours:
            report.append((cp, text, 'EMPTY'))
            continue
        # edit in place: replacing the Glyph object in the table is what left
        # loca inconsistent even once the name matched
        old.coordinates = newg.coordinates
        old.endPtsOfContours = newg.endPtsOfContours
        old.flags = newg.flags
        old.numberOfContours = newg.numberOfContours
        old.program = Program()
        old.recalcBounds(glyf)
        report.append((cp, text, '%d contours, box %dx%d -> %dx%d'
                       % (newg.numberOfContours, w, h,
                          old.xMax - old.xMin, old.yMax - old.yMin)))
    f.save(outpath)
    return report


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else 'preview'
    # candidate edits: image-quality labels, which are plain text and appear
    # in the Quality menu in English mode
    cands = [
        (0xE054, 'OPX', 0.22),
        (0xE055, 'HACK', 0.18),
        (0xE053, 'ZZZ', 0.22),
        (0xE02D, 'YES!', 0.18),
    ]
    if which == 'preview':
        dst = OUT / 'Sony_DI_Icons.PREVIEW.ttf'
        rep = apply_edits(cands, dst)
        print('preview font: %s' % dst)
        for cp, t, s in rep:
            print('  U+%04X  %-6s %s' % (cp, t, s))
        import hashlib
        print('  size %d  md5 %s' % (dst.stat().st_size,
              hashlib.md5(dst.read_bytes()).hexdigest()))
    else:
        dst = OUT / 'Sony_DI_Icons.PATCHED.ttf'
        rep = apply_edits(cands, dst)
        import hashlib
        print('patched font: %s' % dst)
        for cp, t, s in rep:
            print('  U+%04X  %-6s %s' % (cp, t, s))
        print('  size %d  md5 %s' % (dst.stat().st_size,
              hashlib.md5(dst.read_bytes()).hexdigest()))
    # render a before/after sheet for the edited codepoints
    render_sheet([cp for cp, _t, _w in cands])


def render_sheet(cps):
    from fontTools.pens.svgPathPen import SVGPathPen
    import html
    rows = []
    for label, path in (('original', FONT), ('patched', OUT / 'Sony_DI_Icons.PREVIEW.ttf')):
        f = TTFont(path)
        gs = f.getGlyphSet()
        cm = f.getBestCmap()
        cells = []
        for cp in cps:
            nm = cm.get(cp)
            d = ''
            if nm:
                p = SVGPathPen(gs)
                gs[nm].draw(p)
                d = p.getCommands()
            g = f['glyf'][nm] if nm else None
            if g is not None:
                try:
                    g.recalcBounds(f['glyf'])
                    bb = (g.xMin, g.yMin, g.xMax, g.yMax)
                except Exception:
                    bb = (0, 0, 1000, 1000)
            else:
                bb = (0, 0, 1000, 1000)
            cells.append((cp, d, bb))
        rows.append((label, cells))
    parts = ['<!doctype html><meta charset="utf-8"><style>'
             'body{background:#181818;color:#ddd;font:13px monospace}'
             'td,th{padding:6px;text-align:center}svg{background:#2b2b2b;'
             'border:1px solid #555}</style>',
             '<h3>Sony_DI_Icons.ttf &mdash; glyph outline replacement preview</h3><table>']
    parts.append('<tr><th></th>' + ''.join('<th>U+%04X</th>' % c for c in cps) + '</tr>')
    for label, cells in rows:
        parts.append('<tr><th>%s</th>' % label)
        for cp, d, bb in cells:
            x0, y0, x1, y1 = bb
            w = max(1, x1 - x0)
            h = max(1, y1 - y0)
            s = min(140.0 / w, 90.0 / h)
            # centre properly: after the y-flip a font point y maps to ty - y*s,
            # so the glyph's vertical centre lands at cellH/2 only when
            # ty = cellH/2 + (y0+y1)*s/2.  Using ty = cellH/2 + y1*s instead
            # pushed every glyph below the visible area, which is why the first
            # preview showed two apparently blank rows.
            cellH = 110
            tx = (140 - w * s) / 2 - x0 * s
            ty = cellH / 2.0 + (y0 + y1) * s / 2.0
            parts.append('<td><svg width="140" height="%d">'
                         '<g transform="translate(%.2f,%.2f) scale(%.5f,%.5f)">'
                         '<path d="%s" fill="#fff"/></g></svg></td>'
                         % (cellH, tx, ty, s, -s, d))
        parts.append('</tr>')
    parts.append('</table>')
    o = OUT / 'icon_edit_preview.html'
    o.write_text('\n'.join(parts), encoding='utf-8')
    print('preview sheet: %s' % o)


if __name__ == '__main__':
    main()
