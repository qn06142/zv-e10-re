"""Render only the text-label candidates, so they can be identified by eye.

Why this exists
---------------
icon_classify.py proposes "shares a baseline and cap height, and is wider than
tall" as a test for a text label.  Validated against fifteen glyphs whose
identity is already known, it gets six wrong: HOLD, PAL, NTSC and AUTO are
rejected because tightly-set letters touch and the component merge collapses them,
and the transport icons at U+E043/U+E049 pass because two triangles side by side
share a baseline quite as well as two letters do.

Forty per cent wrong on ground truth is not a classifier worth flashing on, and
tuning its thresholds until it fits fifteen samples would be fitting the sample
rather than the font.  So it is demoted to what it is actually good for:
producing a shortlist of 211 candidates out of 1,683.

Identification is then done by looking, which is ground truth rather than a
tuned heuristic, and 211 glyphs is three contact sheets instead of eighteen for
the whole font.
"""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen

sys.path.insert(0, str(Path(__file__).parent))
import icon_classify as ic

OUT = Path(r'C:\Users\qn061\AppData\Local\Temp\opencode\app_res')
FONT = ic.FONT


def main():
    f = TTFont(FONT)
    f.ensureDecompiled()
    gs = f.getGlyphSet()
    glyf = f['glyf']
    cmap = f.getBestCmap()

    cands = []
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
        comps, ncont = ic.components(g, gs, name)
        ok, why = ic.classify(comps, ncont, (g.xMin, g.yMin, g.xMax, g.yMax))
        if ok:
            cands.append(cp)
    # the four known text labels the classifier missed, so they are not lost
    for cp in ic.KNOWN_TEXT:
        if cp not in cands:
            cands.append(cp)
    cands.sort()
    print('candidates: %d (classifier) + known-missed = %d'
          % (len(cands) - 4, len(cands)))

    per = 84
    cell = 92
    cols = 12
    for page in range((len(cands) + per - 1) // per):
        chunk = cands[page * per:(page + 1) * per]
        rows = (len(chunk) + cols - 1) // cols
        parts = ['<!doctype html><meta charset="utf-8"><style>'
                 'body{background:#181818;color:#ddd;font:12px monospace}'
                 'h2{background:#0a0a0a;padding:8px 12px;margin:0;font:13px monospace}'
                 '.g{display:grid;grid-template-columns:repeat(%d,%dpx);gap:8px;padding:10px}'
                 '.c{background:#2b2b2b;border:1px solid #555;height:%dpx;position:relative}'
                 '.c svg{position:absolute;left:0;top:0}'
                 '.l{position:absolute;bottom:1px;left:0;right:0;text-align:center;'
                 'font-size:10px;color:#8a8a8a}</style>'
                 % (cols, cell, cell),
                 '<h2>text-label candidates &mdash; page %d of %d &mdash; '
                 'U+%04X..U+%04X</h2>' % (page + 1,
                                            (len(cands) + per - 1) // per,
                                            chunk[0], chunk[-1]),
                 '<div class="g">']
        for cp in chunk:
            nm = cmap[cp]
            p = SVGPathPen(gs)
            gs[nm].draw(p)
            d = p.getCommands()
            g = glyf[nm]
            x0, y0, x1, y1 = g.xMin, g.yMin, g.xMax, g.yMax
            w = max(1, x1 - x0)
            h = max(1, y1 - y0)
            s = min(cell * 0.82 / w, cell * 0.82 / h)
            tx = (cell - w * s) / 2 - x0 * s
            ty = (cell - h * s) / 2 + y1 * s
            parts.append('<div class="c"><svg width="%d" height="%d">'
                         '<g transform="translate(%.2f,%.2f) scale(%.5f,%.5f)">'
                         '<path d="%s" fill="#fff"/></g></svg>'
                         '<div class="l">U+%04X</div></div>' % (cell, cell, tx, ty, s, -s, d, cp))
        parts.append('</div>')
        o = OUT / ('cands_%d.html' % (page + 1))
        o.write_text('\n'.join(parts), encoding='utf-8')
        print('  %s' % o)


if __name__ == '__main__':
    main()
