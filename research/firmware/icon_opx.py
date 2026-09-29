"""Rewrite the 48 verified labels in the icon font, keeping Sony's rules.

The rule
--------
Every character of a label becomes the next letter of OPX, cycling.  Sony's two
horizontal rules are kept byte-for-byte and everything else is redrawn, so:

    STD          -> OPX
    60           -> OP            (a digit-only label still changes)
    100          -> OPX
    16:9         -> OP:X
    1080/60p     -> OPXO/PXO
    XAVC S       -> OPXO P
    STEADYSHOT   -> OPXOPXOPXO

Digits are replaced too, deliberately.  Preserving them would have left seven of
the twenty-seven barred labels -- 60, 50, 35, 25, 100, 16 and 30 -- completely
unchanged, since those labels are nothing but figures, and a change nobody can
see is not a change.

The separators are drawn rather than preserved
----------------------------------------------
The first attempt kept Sony's slash and colon as well, which meant finding the
contour that is the separator.  That does not work, and the reason is worth
recording: in 1080/30p the slash measures 435x1516 and the digit 1 beside it
measures 545x1495, so "taller than 2.5 times its own width" separates a slash
from a 1 by almost nothing.  Every digit in that label came back classified as a
separator.  Rather than tune a threshold against two nearly identical shapes, the
separator is now simply a character in the string, drawn in the same stroke font
as the letters and landing in the same slot it used to occupy.

The rules are still kept, and that test is sound: a rule is thin, wide, and spans
the glyph, and nothing else in this font looks like that.

Two bugs this file had to fix in itself
---------------------------------------
Closing a rectangle one point early.  The contour end was recorded as
``(i + 1) in re`` where the pen already indexes from zero, so every drawn
rectangle was cut a point short and the last point of the glyph was left outside
any contour.  fontTools reports that as "too much glyph data" and then reads
every following glyph from the wrong offset, so all 48 targets came back with
coordinates like yMax=104264 -- outside the int16 range the format allows.  The
glyphs looked correct in memory and were corrupt on disk, which is the worst
possible place for a bug to live.  ends[-1] == len(coordinates) - 1 is now
asserted rather than assumed.

Boxes growing past their originals.  Fitting a stroke to the ink box of the
original letters pushes half a stroke width beyond it on every side; 720/60p came
out 130 units taller, enough to collide with whatever sits above it.  The box is
now inset by half the stroke width first, so the finished ink lands inside.

Nothing here writes to the camera.
"""
import hashlib
import sys
from array import array
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
from fontTools.ttLib.tables.ttProgram import Program

sys.path.insert(0, str(Path(__file__).parent))
import icon_bars as ib
import icon_targets_verified as tv
from icon_edit import STROKES, thicken

FONT = ib.FONT
OUT = Path(r'C:\Users\qn061\AppData\Local\Temp\opencode\app_res')

MARKER = 'OPX'
WEIGHT = 0.20

# characters that are drawn as themselves rather than replaced by a marker letter.
# The colon is built from two short vertical segments rather than two horizontal
# ones: a horizontal segment becomes a rectangle `thick` tall, and thick scales
# with the cell width, so on a narrow cell the two dots came out as wide flat
# dashes and 16:9 read "OP-X".
DRAWN = set('/:+.')
DRAWN_STROKES = {
    '/': [(0, 0, 1, 1)],
    ':': [(0.5, 0.12, 0.5, 0.24), (0.5, 0.76, 0.5, 0.88)],
    '+': [(0.5, 0.12, 0.5, 0.88), (0.12, 0.5, 0.88, 0.5)],
}


def marker_string(label):
    """the label with every replaced character cycled through OPX"""
    out = []
    k = 0
    for ch in label:
        if ch == ' ':
            out.append(' ')
        elif ch in DRAWN:
            out.append(ch)
        else:
            out.append(MARKER[k % len(MARKER)])
            k += 1
    return ''.join(out)


def contour_ranges(g):
    out = []
    start = 0
    for e in g.endPtsOfContours:
        out.append((start, e))
        start = e + 1
    return out


def cbox(coords, a, b):
    xs = [coords[i][0] for i in range(a, b + 1)]
    ys = [coords[i][1] for i in range(a, b + 1)]
    return (min(xs), min(ys), max(xs), max(ys))


def is_rule(box, gw, gh):
    """a rule is thin, wide, and sits above or below the text

    Requiring it to span half the glyph was too strict and behaved
    inconsistently: HD HQ+ kept its rules while HD SP, HD LP and HD HQ did not,
    purely because the composite labels are wider and their rules are a smaller
    fraction of the whole.  Position is the better test.  A rule belongs to the
    frame, so it lies outside the band the letters occupy; a crossbar belongs to
    a letter, and in this font a letter is a single contour, so a crossbar never
    arrives here as a contour of its own.
    """
    x0, y0, x1, y1 = box
    w = x1 - x0
    h = y1 - y0
    if w <= 0 or h <= 0:
        return False
    if not ib.is_bar(box, gw, gh):
        return False
    if w < 0.25 * gw:
        return False
    cy = (y0 + y1) / 2.0
    return cy <= 0.30 * gh or cy >= 0.70 * gh


def draw_run(text, x0, y0, x1, y1, weight, thickness_scale=0.14):
    """rectangle contours for `text` fitted inside the given box

    The box is the ink extent of the original letters, so the box is inset by
    half a stroke width before layout: centring a stroke on the outline would
    otherwise leave ink outside the original bounds.
    """
    if not text or x1 <= x0 or y1 <= y0:
        return [], []
    n = max(1, len(text))
    cellw = (x1 - x0) / float(n)
    sw = cellw * (1.0 - thickness_scale)
    sh = y1 - y0
    thick = weight * min(sw, sh) * 0.9
    h = thick / 2.0
    x0, x1 = x0 + h, x1 - h
    y0, y1 = y0 + h, y1 - h
    if x1 <= x0 or y1 <= y0:
        return [], []
    cellw = (x1 - x0) / float(n)
    sw = cellw * (1.0 - thickness_scale)
    sh = y1 - y0
    thick = weight * min(sw, sh) * 0.9
    coords, ends = [], []
    ox = x0 + (cellw - sw) / 2.0
    for ch in text:
        if ch != ' ':
            segs = DRAWN_STROKES.get(ch) or STROKES.get(ch.upper())
            if segs:
                # x maps straight into the cell.  Scaling by the character's own
                # extent was wrong for punctuation: a mark spanning 0.4..0.6 was
                # stretched to the full cell width, which is how the colon in
                # 16:9 turned into a dash.  O, P and X all span the cell anyway.
                for (ax, ay, bx, by) in segs:
                    r = thicken(ox + ax * sw, y0 + ay * sh,
                                ox + bx * sw, y0 + by * sh, thick)
                    if not r:
                        continue
                    base = len(coords)
                    for (px, py) in r:
                        coords.append((int(round(px)), int(round(py))))
                    ends.append(base + 3)
        ox += cellw
    return coords, ends


def patch_one(f, cp, label, weight=WEIGHT):
    cmap = f.getBestCmap()
    name = cmap.get(cp)
    if name is None:
        return 'UNMAPPED'
    glyf = f['glyf']
    g = glyf[name]
    try:
        g.recalcBounds(glyf)
    except Exception:
        return 'NOBBOX'
    gw = g.xMax - g.xMin
    gh = g.yMax - g.yMin
    if gw <= 0 or gh <= 0:
        return 'DEGENERATE'
    coords = g.coordinates
    flags = g.flags
    ranges = contour_ranges(g)

    keep = []
    tb = None
    for (a, b) in ranges:
        box = cbox(coords, a, b)
        if is_rule(box, gw, gh):
            keep.append((a, b))
        else:
            tb = box if tb is None else (min(tb[0], box[0]), min(tb[1], box[1]),
                                         max(tb[2], box[2]), max(tb[3], box[3]))
    if tb is None:
        return 'NOTEXT'
    if len(keep) > 4:
        return 'TOOMANYRULES(%d)' % len(keep)
    if tb[2] - tb[0] < 20 or tb[3] - tb[1] < 20:
        return 'TEXTBOXTOOSMALL'

    new_coords, new_flags, new_ends = [], [], []
    for (a, b) in keep:                       # Sony's rules, untouched
        for i in range(a, b + 1):
            new_coords.append((coords[i][0], coords[i][1]))
            new_flags.append(flags[i])
        new_ends.append(len(new_coords) - 1)

    rc, re = draw_run(marker_string(label), tb[0], tb[1], tb[2], tb[3], weight)
    for i in range(len(rc)):
        new_coords.append(rc[i])
        new_flags.append(0)
        if i in re:                            # zero-based: see the note above
            new_ends.append(len(new_coords) - 1)

    if not new_ends:
        return 'EMPTY'
    if new_ends[-1] != len(new_coords) - 1:
        return ('ORPHANPOINT(%d coords, last end %d)'
                % (len(new_coords), new_ends[-1]))
    if max(max(abs(c[0]), abs(c[1])) for c in new_coords) > 32767:
        return 'OUTOFINT16'

    g.coordinates = GlyphCoordinates(new_coords)
    g.flags = array('B', new_flags)
    g.endPtsOfContours = new_ends
    g.numberOfContours = len(new_ends)
    g.program = Program()
    g.recalcBounds(glyf)
    if max(abs(g.xMin), abs(g.yMin), abs(g.xMax), abs(g.yMax)) > 32767:
        return 'BOXOUTOFINT16'
    return 'ok  %d->%d contours, %d rules kept, box %dx%d -> %dx%d' % (
        len(ranges), len(new_ends), len(keep), gw, gh,
        g.xMax - g.xMin, g.yMax - g.yMin)


def main():
    dst = OUT / 'Sony_DI_Icons.OPX.ttf'
    f = TTFont(FONT)
    f.ensureDecompiled()
    adv_before = {n: f['hmtx'][n][0] for n in f.getGlyphOrder()}

    bad = []
    for cp in sorted(tv.TARGETS):
        label = tv.TARGETS[cp]
        st = patch_one(f, cp, label)
        if not st.startswith('ok'):
            bad.append((cp, label, st))
        print('  U+%04X  %-13s -> %-13s %s'
              % (cp, label, marker_string(label), st))
    f.save(dst)

    o1 = TTFont(FONT)
    o1.ensureDecompiled()
    g2 = TTFont(dst)
    g2.ensureDecompiled()
    names = {o1.getBestCmap()[c] for c in tv.TARGETS}
    same = 0
    oor = []
    for n in o1.getGlyphOrder():
        b = g2['glyf'][n]
        try:
            b.recalcBounds(g2['glyf'])
        except Exception:
            pass
        if max(abs(b.xMin), abs(b.yMin), abs(b.xMax), abs(b.yMax)) > 32767:
            oor.append(n)
        if n in names:
            continue
        a = o1['glyf'][n]
        try:
            a.recalcBounds(o1['glyf'])
        except Exception:
            continue
        if (a.numberOfContours == b.numberOfContours
                and (a.xMin, a.yMin, a.xMax, a.yMax)
                == (b.xMin, b.yMin, b.xMax, b.yMax)):
            same += 1
    moved = [n for n in o1.getGlyphOrder() if g2['hmtx'][n][0] != adv_before[n]]

    print()
    print('failures: %d' % len(bad))
    for cp, label, st in bad:
        print('  U+%04X %s: %s' % (cp, label, st))
    print()
    print('=== integrity ===')
    print('  glyphs            %d -> %d' % (len(o1.getGlyphOrder()), len(g2.getGlyphOrder())))
    print('  cmap entries      %d -> %d   identical: %s'
          % (len(o1.getBestCmap()), len(g2.getBestCmap()),
             o1.getBestCmap() == g2.getBestCmap()))
    print('  advance widths moved: %d' % len(moved))
    print('  glyphs outside int16: %d' % len(oor))
    print('  non-target glyphs with identical outline and box: %d of %d'
          % (same, len(o1.getGlyphOrder()) - len(names)))
    print('  size  %d  md5 %s' % (dst.stat().st_size,
          hashlib.md5(dst.read_bytes()).hexdigest()))
    print('  orig  %d  md5 %s' % (FONT.stat().st_size,
          hashlib.md5(FONT.read_bytes()).hexdigest()))


if __name__ == '__main__':
    main()
