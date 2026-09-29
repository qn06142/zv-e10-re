"""Verify the exact codepoint of every glyph targeted for replacement.

Why this file exists
--------------------
The target list was read off contact sheets, and one codepoint was already
misread that way: U+E03D ("HOLD") was recorded as U+E02D, which is actually the
hand-and-warning pictogram.  Editing a glyph because its label looked right is
exactly the failure this project keeps making, and a font is a place where it
would be invisible until the screen was wrong.

So the list is defined by *what the glyph should be*, and this renders precisely
those codepoints for confirmation before anything is modified.  Each entry states
the expected reading, so the sheet can be checked against the claim rather than
admired.

The three families the user asked for
--------------------------------------
  1. "the one with the bars and a number in between" -- the image-size and
     aspect-ratio family, which Sony draws with a rule above and below the
     figures: SP, HQ, LP, 16:9, 4:3, STD, 35, 25, 50, 60, 100, XP, HD XP,
     HQ+, FX, FH, FS.
  2. "the resolutions and the xavc" -- the recording-format family: the
     1080/720/480/576/2160 line rates, the SCAN variants, and AVCHD / XAVC /
     XAVC S.
  3. "that steadyshot one" -- STEADYSHOT, identified by the user from the
     waving-hand pictogram that accompanies it in the UI.

Nothing is written and no font is modified here.  This only establishes that the
list names what it claims to name.
"""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen

FONT = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share\app\Sony_DI_Icons.ttf')
OUT = Path(r'C:\Users\qn061\AppData\Local\Temp\opencode\app_res')

# (codepoint, what it should read, family)
TARGETS = [
    # --- 1. bars above and below: image size / aspect ratio -----------------
    (0xE03E, 'SP',      'bars'),
    (0xE03F, 'HQ',      'bars'),
    (0xE040, 'LP',      'bars'),
    (0xE041, '16:9',    'bars'),
    (0xE095, '4:3',     'bars'),
    (0xE506, 'STD',     'bars'),
    (0xE528, '60',      'bars'),
    (0xE52C, '50',      'bars'),
    (0xE539, '35',      'bars'),
    (0xE53A, '25',      'bars'),
    (0xE540, '100',     'bars'),
    (0xE101, 'XP',      'bars'),
    (0xE102, 'HD XP',   'bars'),
    (0xE103, 'HQ+',     'bars'),
    (0xE146, 'FX',      'bars'),
    (0xE147, 'FH',      'bars'),
    (0xE148, 'FS',      'bars'),
    # --- 2. resolutions -----------------------------------------------------
    (0xE1F9, '1080/30p',     'res'),
    (0xE1FA, '1080/24p',     'res'),
    (0xE1FB, '720/60p',      'res'),
    (0xE1FD, '480/30p SCAN', 'res'),
    (0xE1FE, '480/24p SCAN', 'res'),
    (0xE200, '1080/25p',     'res'),
    (0xE201, '720/50p',      'res'),
    (0xE203, '576/25p SCAN', 'res'),
    (0xE3E8, '1080/60p',     'res'),
    (0xE3E9, '1080/50p',     'res'),
    (0xE558, '2160/30p',     'res'),
    (0xE55C, '2160/25p',     'res'),
    (0xE55D, '2160/24p',     'res'),
    # --- 2b. codec ----------------------------------------------------------
    (0xE536, 'AVCHD',  'codec'),
    (0xE537, 'XAVC',   'codec'),
    (0xE538, 'XAVC S', 'codec'),
    # --- 3. steadyshot ------------------------------------------------------
    (0xE21C, 'STEADYSHOT', 'steadyshot'),
]

# the pictogram the user identified STEADYSHOT by, rendered alongside so the
# association can be confirmed rather than assumed
COMPANION = 0xE2D1


def main():
    f = TTFont(FONT)
    f.ensureDecompiled()
    gs = f.getGlyphSet()
    glyf = f['glyf']
    cmap = f.getBestCmap()

    missing = [cp for cp, _r, _fam in TARGETS if cp not in cmap]
    if missing:
        print('NOT MAPPED: %s' % ['0x%04X' % c for c in missing])
        return
    print('all %d target codepoints are mapped' % len(TARGETS))

    cell = 150
    cols = 8
    items = list(TARGETS) + [(COMPANION, '(companion pictogram)', 'ref')]
    rows = (len(items) + cols - 1) // cols
    parts = ['<!doctype html><meta charset="utf-8"><style>'
             'body{background:#181818;color:#ddd;font:12px monospace}'
             'h2{background:#0a0a0a;padding:8px 12px;margin:0;font:13px monospace}'
             '.g{display:grid;grid-template-columns:repeat(%d,%dpx);gap:10px;padding:12px}'
             '.c{background:#2b2b2b;border:1px solid #666;padding:6px}'
             '.f{height:%dpx;position:relative}.f svg{position:absolute;left:0;top:0}'
             '.cp{color:#ffd479;font-size:11px}.ex{color:#8fe08f;font-size:10px}'
             '.fm{color:#7a7a7a;font-size:9px}</style>'
             % (cols, cell + 12, cell),
             '<h2>flash targets &mdash; confirm each glyph reads as claimed '
             'before editing</h2><div class="g">']
    for cp, expect, fam in items:
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
        parts.append(
            '<div class="c"><div class="f"><svg width="%d" height="%d">'
            '<g transform="translate(%.2f,%.2f) scale(%.5f,%.5f)">'
            '<path d="%s" fill="#fff"/></g></svg></div>'
            '<div class="cp">U+%04X</div>'
            '<div class="ex">expect: %s</div>'
            '<div class="fm">%s &middot; %d contours &middot; box %dx%d</div></div>'
            % (cell, cell, tx, ty, s, -s, d, cp, expect, fam,
               g.numberOfContours, w, h))
    parts.append('</div>')
    o = OUT / 'targets_verify.html'
    o.write_text('\n'.join(parts), encoding='utf-8')
    print('wrote %s' % o)
    print()
    from collections import Counter
    print('by family: %s' % dict(Counter(f for _c, _r, f in TARGETS)))
    for cp, expect, fam in TARGETS:
        nm = cmap[cp]
        g = glyf[nm]
        try:
            g.recalcBounds(glyf)
        except Exception:
            pass
        print('  U+%04X  %-6s %-12s %3d contours  %5d x %-5d  adv %d'
              % (cp, expect, fam, g.numberOfContours,
                 g.xMax - g.xMin, g.yMax - g.yMin,
                 f['hmtx'][nm][0]))


if __name__ == '__main__':
    main()
