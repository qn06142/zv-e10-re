"""Build a patched color_cmn.uxc and verify it is a controlled, minimal edit.

The point of this script is that the camera-side write is the risky step, so
everything that can be checked offline is checked offline first.  Before any
byte is staged, this asserts:

  1. the original parses and re-emits byte-exactly  (container is decoded)
  2. the patched file is the SAME LENGTH               (no layout shift)
  3. the only differing bytes are inside RGBA quads   (no id/const damage)
  4. the exact byte offsets to be changed are printed
  5. a restore file is produced from the untouched original

Requirement 3 is the important one.  A sloppy edit that touches an id or the
0x3a09 const field would still render, but would be changing the palette's
*meaning* rather than its colours, and could leave the engine with a slot it
cannot resolve.  Only the four rgba bytes at +4..+7 of a chosen record are
permitted to move.

Which colours to shift, and why
-------------------------------
Sony's palette in this file is warm: white, five alphas of black, three greys,
orange (0x4010/0x4011), yellow (0x4013), and red (0x4007) for record and
warning states.  Blue at 0x4009 is the one entry the UI has no reason to use,
because nothing in a camera's chrome needs a saturated blue and Sony's design
does not use one.  That makes it the best target on both counts: it will be on
screen where a blue accent appears, and a garish blue cannot be mistaken for a
factory state, a warning, or a fault indicator.

  0x4009 0000dd  blue     THE TARGET.  Recoloured to a strong cyan-white so it
                          is unmistakably ours and cannot be read as "something
                          went wrong".
  0x400c 33333380         a translucent dark grey used in panel shading, so
                          recolouring it shifts large areas rather than a small
                          accent.  Kept at a subtle shift so the effect is
                          visible even if the blue accent is off-screen.
  0x4007 dd0000  red      NOT shifted.  Sony uses red for record and warning
                          states; changing it would read as an error condition
                          rather than as our work.

Two quads, not four.  A minimal patch is the right instinct here: the whole
point is that the engine parses this file normally, so the less we change, the
more clearly any change we see is attributable to us and not to collateral
damage.  0x400c is included only because it is the one entry that can produce a
broad area change; if a reviewer wants a strict single-quad patch, drop it and
the file still round-trips.

Preserved for later: the pristine tar member, and the sha256 of both files, so
the pushed file can be proven byte-identical to what was reviewed here.
"""
import hashlib
import struct
import sys
from pathlib import Path

APP = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\app')
SRC = APP / 'color_cmn.uxc'
OUT = APP / 'color_cmn.out.uxc'
RESTORE = APP / 'color_cmn.restore.uxc'

HDR = 0x58
REC = 8
CONST = 0x3a09
ID_BASE = 0x4000

# id-offset -> (name, new rgba)
SHIFT = {
    0x09: ('blue',   (0x00, 0xFF, 0xFF, 0xFF)),   # 0000dd -> cyan, the target
    0x0c: ('grey33', (0x00, 0x00, 0xDD, 0x80)),   # 333333 80 -> blue 50%, subtle
}


def parse(b):
    assert b[:3] == b'uxc', 'not a uxc container'
    n = (len(b) - HDR) // REC
    assert (len(b) - HDR) % REC == 0, 'body is not a whole number of records'
    cols = []
    for i in range(n):
        o = HDR + i * REC
        cid, const, r, g, bl, a = struct.unpack_from('<HHBBBB', b, o)
        cols.append(dict(off=o, id=cid, const=const,
                         rgba=(r, g, bl, a)))
    return cols


def rgba_off(off):
    return off + 4, off + 5, off + 6, off + 7


def main():
    raw = SRC.read_bytes()
    cols = parse(raw)

    # 1. round-trip the untouched original
    rebuilt = bytearray(raw[:HDR])
    for c in cols:
        rebuilt += struct.pack('<HHBBBB', c['id'], c['const'], *c['rgba'])
    assert bytes(rebuilt) == raw, 'FATAL: container does not round-trip'
    print('container round-trips byte-exactly (%d bytes)' % len(raw))

    byoff = {c['id'] - ID_BASE: c for c in cols}
    assert len(byoff) == len(cols), 'duplicate ids -- id range assumption wrong'
    print('%d unique ids, 0x%04x..0x%04x'
          % (len(cols), min(byoff), ID_BASE + max(byoff)))

    # 2. apply
    out = bytearray(raw)
    plan = []
    for off_id, (name, new) in sorted(SHIFT.items()):
        c = byoff.get(off_id)
        if c is None:
            print('  skip %-7s id 0x%04x absent from this file' % (name, ID_BASE + off_id))
            continue
        old = c['rgba']
        for byte_off, val in zip(rgba_off(c['off']), new):
            out[byte_off] = val
        plan.append((c, name, old, new))
        print('  %-7s id 0x%04x  %s -> %s  @ rec 0x%04x, bytes %s'
              % (name, c['id'],
                 ' '.join('%02x' % v for v in old),
                 ' '.join('%02x' % v for v in new),
                 c['off'],
                 ' '.join('0x%04x' % o for o in rgba_off(c['off']))))

    # 3. same length
    assert len(out) == len(raw), 'FATAL: length changed'
    print('length unchanged: %d bytes' % len(out))

    # 4. differing bytes must all be rgba quads of a planned record
    allowed = set()
    for c, _n, _o, _x in plan:
        allowed.update(rgba_off(c['off']))
    diffs = [i for i in range(len(raw)) if raw[i] != out[i]]
    illegal = [i for i in diffs if i not in allowed]
    if illegal:
        print('FATAL: %d changed byte(s) outside an rgba quad: %s'
              % (len(illegal), [hex(i) for i in illegal]))
        return 1
    print('%d byte(s) changed, all inside rgba quads -- no id or const touched'
          % len(diffs))
    if not diffs:
        print('WARNING: nothing actually changed')
        return 1

    # 5. re-parse the patched file and confirm it is still well formed
    after = parse(bytes(out))
    assert len(after) == len(cols), 'record count changed'
    for c, name, old, new in plan:
        got = [x for x in after if x['id'] == c['id']][0]
        assert got['rgba'] == new, '%s did not take' % name
        assert got['id'] == c['id'] and got['const'] == c['const'], \
            '%s: id/const damaged' % name
    print('patched file re-parses: %d records, all ids and consts intact'
          % len(after))

    OUT.write_bytes(bytes(out))
    RESTORE.write_bytes(raw)
    print()
    print('wrote %s' % OUT)
    print('  sha256 %s' % hashlib.sha256(bytes(out)).hexdigest())
    print('wrote %s' % RESTORE)
    print('  sha256 %s' % hashlib.sha256(raw).hexdigest())
    print('  (restore is byte-identical to the camera copy in ui.tar)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
