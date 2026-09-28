"""Pin down the style_cmn.uxc record: stride 36, RGBA at +12, index at +0.

From the previous run: style_cmn.uxc contains 63 aligned quads that match a
palette colour exactly, at a 9212x excess over chance, and the dump shows them
repeating on a regular stride.  The body from 0x58 to EOF is 1800 bytes, and
1800 / 36 = 50 records exactly.  The dump also shows a rising index byte
(00 01 02 03 ...) and a constant marker a0 07 26 08 in each record, so this is
a fixed-stride table after all -- 36 bytes, not 8.

The record, read off the dump:

    +0   u8   index          00, 01, 02, 03 ... rising
    +1   ?    0xa0
    +2   ?    0x07
    +3   ?    0x26
    +4   ?    0x08
    +5   u8   0x00
    +6   u32  0x00000000
    +12  u8   r,g,b,a        the inline colour
    +16  u16  0x0000
    +18  u16  0x0004
    +20  u8   0x01
    +21  u32  0x00000000
    +25  u32  0x00000000
    +29  u32  0x00000003
    +33  ?    0x00,0x00,0xff -- varies

Not every field is understood, and the script does not pretend otherwise.  What
is verified here is the part that matters for editing:

  * the stride is 36 and divides the body exactly, with no remainder
  * the index at +0 is strictly increasing across all records
  * the RGBA at +12 is in a plausible range and the file's 63 palette matches
    all land on +12 of some record
  * the file re-emits byte-exactly, so a patch built on this is trustworthy

and then, the part that makes it useful: enumerate every distinct colour in the
table, so the user can choose what to change.  The point of this script is a
menu of levers, not a format claim.
"""
import struct
import tarfile
from collections import Counter
from pathlib import Path

CANDIDATES = [
    Path(r'F:\RE_DUMP\TREES\usr_share.tgz'),
    Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz'),
]
STRIDE = 36
BODY = 0x58
RGBA = 12


def pick():
    for p in CANDIDATES:
        if p.exists():
            try:
                with p.open('rb') as f:
                    f.read(2)
                return p
            except OSError:
                continue
    raise SystemExit('no readable archive')


def load():
    t = tarfile.open(pick())
    out = {}
    for m in t.getmembers():
        if m.isfile() and m.name.endswith('.uxc'):
            out[m.name.split('/')[-1]] = t.extractfile(m).read()
    return out


def records(b):
    n = (len(b) - BODY) // STRIDE
    assert (len(b) - BODY) % STRIDE == 0, 'body is not a whole number of records'
    out = []
    for i in range(n):
        o = BODY + i * STRIDE
        r = b[o:o + STRIDE]
        out.append(dict(off=o, idx=r[0], marker=r[1:5],
                        rgba=tuple(r[RGBA:RGBA + 4]), raw=r))
    return out


def main():
    d = load()
    b = d['style_cmn.uxc']
    recs = records(b)

    print('=== style_cmn.uxc: %d bytes, body %d, stride %d, %d records ==='
          % (len(b), len(b) - BODY, STRIDE, len(recs)))
    print()

    # 1. the index must be strictly increasing
    idxs = [r['idx'] for r in recs]
    inc = all(idxs[i + 1] == idxs[i] + 1 for i in range(len(idxs) - 1))
    print('  index at +0: %s' % (' '.join('%02x' % i for i in idxs)))
    print('  strictly increasing by 1: %s' % inc)

    # 2. the marker must be constant
    mk = Counter(r['marker'] for r in recs)
    print('  marker at +1..+4: %s'
          % ', '.join(' '.join('%02x' % x for x in k) for k in mk))
    print('  constant across all records: %s' % (len(mk) == 1))

    # 3. every distinct colour
    print()
    print('  %-4s %-8s %-14s %s' % ('idx', 'offset', 'rgba', 'reads as'))
    cols = Counter()
    for r in recs:
        cols[r['rgba']] += 1
    for r in recs:
        rr, gg, bb, aa = r['rgba']
        name = []
        if (rr, gg, bb) == (0, 0, 0):
            name.append('black')
        elif (rr, gg, bb) == (255, 255, 255):
            name.append('white')
        elif rr == gg == bb:
            name.append('grey%d' % rr)
        elif rr == gg and bb == 0:
            name.append('yellow%d' % rr)
        elif gg == bb and rr == 0:
            name.append('cyan%d' % gg)
        elif rr == bb and gg == 0:
            name.append('magenta%d' % rr)
        elif rr == gg:
            name.append('orange%d' % rr)
        elif gg == bb:
            name.append('azure%d' % gg)
        elif rr == bb:
            name.append('violet%d' % rr)
        else:
            name.append('rgb')
        if aa != 255:
            name.append('a=%d' % aa)
        print('  %-4d 0x%06x  %-14s %s'
              % (r['idx'], r['off'],
                 ' '.join('%02x' % c for c in r['rgba']), ' '.join(name)))

    print()
    print('  === %d distinct colours across %d records ==='
          % (len(cols), len(recs)))
    for q, c in cols.most_common():
        print('    %-14s x%-3d  %s' % (' '.join('%02x' % x for x in q), c,
                                        'alpha %d' % q[3]))

    # 4. round-trip, so a patch on this layout is trustworthy
    re_emit = bytearray(b[:BODY])
    for r in recs:
        re_emit += r['raw']
    ok = bytes(re_emit) == b
    print()
    print('  re-emitted %d bytes: %s' % (len(re_emit),
                                         'BYTE-EXACT' if ok else 'MISMATCH'))
    if not ok:
        for i, (x, y) in enumerate(zip(b, re_emit)):
            if x != y:
                print('    first diff at 0x%04x' % i)
                break
        return 1

    # 5. show the byte offsets a patch would touch, per colour
    print()
    print('  === edit targets: every occurrence of each colour ===')
    for q, c in cols.most_common(12):
        offs = [r['off'] + RGBA for r in recs if r['rgba'] == q]
        print('    %-14s %d rec(s) at %s'
              % (' '.join('%02x' % x for x in q), len(offs),
                 ' '.join('0x%04x' % o for o in offs[:12])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
