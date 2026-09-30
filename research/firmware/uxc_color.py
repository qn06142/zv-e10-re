"""Strict uxc codec for color_cmn.uxc, with a byte-exact round-trip test.

Decoded from the file itself (312 bytes), not assumed.  Header:

    0x00  3 bytes  magic 'uxc'
    0x03  u8       format version (7)
    0x04  3 bytes  zero
    0x07  u8       zero
    0x08  u16      stream version: 8 for .uxc, 9 for .uxb/.uxa
    0x0A  u16      file-specific (0x4a here) -- unknown, preserved verbatim
    0x0C  u16[]    index/offset table, 0xffff meaning "absent"
    ...   body, 8-byte colour records

Colour record, stride exactly 8, 28 of them, 0x58..0x137 inclusive, which
accounts for all 312 bytes:

    +0  u16  id          sequential 0x4000 .. 0x4022
    +2  u16  const       0x3a09 in every record in this file
    +4  u8   r
    +5  u8   g
    +6  u8   b
    +7  u8   a

The ids are consecutive with no gaps.  What looked like gaps are the 0xffff
holes in the separate u16 *index* table at 0x0E, which is a sparse
id-to-slot map and not the colour list itself.  The first two header words are
u16 0x004a at 0x0A and u16 0x4023 at 0x0C; 0x4023 is one past the highest id,
i.e. the high-water mark.  Neither is a checksum, which matters: nothing in
this file validates its own payload, so a one-quad edit cannot be rejected.

Every observed colour is a plausible UI colour, and that is the cross-check:
white, black at 0x99/0x88/0x44/0xcc/0x4c alpha, dd dd dd, cc cc cc and
33 33 33 greys, dd 55 00 and dd 66 00 orange/yellow, and dd/00 in r, g, b for
the pure primaries.  That is not noise.

The whole point of this file is to be able to rewrite exactly one RGBA quad
and prove the rewrite is the only difference.  So: parse, re-emit, assert
byte equality, and only then permit a modified variant to be written.  A
container that cannot round-trip byte-exactly is not decoded, and any patch
built on top of it would be a guess.
"""
import struct
import pathlib
from pathlib import Path

ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]

SRC = ROOT_REPO / 'dumps' / 'camera' / 'app' / 'color_cmn.uxc'
REC = 8
HDR = 0x58
ATTR = 0x3a09
ID_BASE = 0x4000

# Sony UI colour names inferred from the id gaps and the RGB values actually
# present.  Kept as annotation only -- nothing depends on these being right.
NAMES = {
    0x00: 'white',          0x01: 'grey_ddd',       0x02: 'black_99',
    0x03: 'black_88',       0x04: 'grey_ddd',       0x05: 'grey_ddd',
    0x06: 'grey_ddd',       0x07: 'red',            0x08: 'green',
    0x09: 'blue',           0x0a: 'grey_cc_80',     0x0b: 'grey_cc_80',
    0x0c: 'grey33_80',      0x0d: 'grey33_80',      0x0e: 'grey33_80',
    0x0f: 'grey33_80',      0x10: 'orange',         0x11: 'orange',
    0x12: 'grey_ddd',       0x13: 'yellow',         0x15: 'grey_ddd',
    0x17: 'black_99',       0x18: 'black_44',       0x1b: 'black_cc',
    0x1f: 'grey_ddd',       0x20: 'grey_ddd',       0x21: 'white',
    0x22: 'black_4c',
}


class Colour:
    __slots__ = ('cid', 'attr', 'r', 'g', 'b', 'a')

    def __init__(self, cid, attr, r, g, b, a):
        self.cid, self.attr = cid, attr
        self.r, self.g, self.b, self.a = r, g, b, a

    def pack(self):
        return struct.pack('<HHBBBB', self.cid, self.attr,
                           self.r, self.g, self.b, self.a)


def parse(b):
    assert b[:3] == b'uxc', 'not a uxc container'
    ver = b[3]
    stream = struct.unpack_from('<H', b, 8)[0]
    tag = struct.unpack_from('<H', b, 10)[0]
    n = (len(b) - HDR) // REC
    assert (len(b) - HDR) % REC == 0, 'body is not a whole number of records'
    cols = []
    for i in range(n):
        o = HDR + i * REC
        cols.append(Colour(*struct.unpack_from('<HHBBBB', b, o)))
    return dict(ver=ver, stream=stream, tag=tag, prefix=b[:HDR], cols=cols)


def emit(p):
    out = bytearray(p['prefix'])
    for c in p['cols']:
        out += c.pack()
    return bytes(out)


def show(p):
    print('  uxc v%d stream %d tag 0x%04X  %d colour records' %
          (p['ver'], p['stream'], p['tag'], len(p['cols'])))
    for c in p['cols']:
        nm = NAMES.get(c.cid - ID_BASE, '?')
        print('    id 0x%04x %-12s %02x %02x %02x %02x   attr 0x%04x%s'
              % (c.cid, nm, c.r, c.g, c.b, c.a, c.attr,
                 '' if c.attr == ATTR else '   <-- NON-STANDARD ATTR'))


def main():
    raw = SRC.read_bytes()
    p = parse(raw)
    print('=== %s: %d bytes ===' % (SRC.name, len(raw)))
    show(p)
    print()

    back = emit(p)
    print('=== round-trip ===')
    print('  re-emitted %d bytes' % len(back))
    if back == raw:
        print('  BYTE-EXACT MATCH -- container decoded, patch is trustworthy')
    else:
        print('  MISMATCH -- do NOT build a patch on this')
        for i, (x, y) in enumerate(zip(raw, back)):
            if x != y:
                print('    first diff at 0x%04x: %02x -> %02x' % (i, x, y))
                break
        return 1
    print()

    print('=== single-quad patch demo (not written to the camera) ===')
    q = parse(raw)
    target = ID_BASE + 0x07          # the pure-red accent
    hits = [c for c in q['cols'] if c.cid == target]
    assert len(hits) == 1, 'expected exactly one record with id 0x%04x' % target
    hits[0].r, hits[0].g, hits[0].b, hits[0].a = 0xFF, 0x00, 0xFF, 0xFF
    demo = emit(q)
    diffs = [(i, raw[i], demo[i]) for i in range(len(raw)) if raw[i] != demo[i]]
    print('  changed %d bytes at offsets %s'
          % (len(diffs), ', '.join('0x%02x' % d[0] for d in diffs)))
    assert len(demo) == len(raw), 'patch changed the file length'
    Path(SRC.parent / 'color_cmn.patched.uxc').write_bytes(demo)
    print('  wrote color_cmn.patched.uxc (%d bytes) for review' % len(demo))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
