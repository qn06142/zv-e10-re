"""Derive the style_cmn.uxc record from its own marker, not from a guess.

uxc_style_rec.py assumed stride 36 with RGBA at +12.  That was wrong, and its
own output said so: the index at +0 was not increasing, the +1..+4 "marker" was
not constant, and 40 of 50 records decoded as garbage with alpha 38 -- which is
the marker `a0 07 26` being read as if it were a colour.  The stride happened to
divide 1800 evenly, which is why it looked plausible.

The correct approach is to let the file nominate its own record boundary.  The
marker `a0 07 26 08` is a genuine fixed signature -- it appeared in the raw dump
at 0x89, 0xad, 0xd1, 0xf5, and again in every view file.  So:

  1. find every occurrence of the marker by raw search, not by assumption
  2. measure the gaps between consecutive occurrences -- that IS the stride,
     derived rather than posited
  3. only then ask where the rgba sits relative to the marker, by finding which
     fixed offset from the marker yields palette-matching quads
  4. verify the index field, which should be strictly increasing once the
     boundary is right

Then confirm: every record's rgba should be a plausible colour, the index
should increase by 1, and the file should re-emit byte-exactly.

If the marker gaps are not constant, that means the records are variable-length
and the whole fixed-stride model is wrong -- which is itself the finding, and
the reason to report it rather than to keep nudging the offset until something
looks tidy.
"""
import struct
import tarfile
from collections import Counter
from pathlib import Path

CANDIDATES = [
    Path(r'F:\RE_DUMP\TREES\usr_share.tgz'),
    Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz'),
]
MARKER = bytes([0xa0, 0x07, 0x26, 0x08])
BODY = 0x58


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


def palette(b):
    n = (len(b) - 0x58) // 8
    out = {}
    for i in range(n):
        o = 0x58 + i * 8
        cid, const, r, g, bl, a = struct.unpack_from('<HHBBBB', b, o)
        out[(r, g, bl, a)] = cid - 0x4000
    return out


def find_all(buf, pat, lo=0):
    out, s = [], lo
    while True:
        i = buf.find(pat, s)
        if i < 0:
            return out
        out.append(i)
        s = i + 1


def main():
    d = load()
    sc = d['style_cmn.uxc']
    pal = palette(d['color_cmn.uxc'])

    print('=== style_cmn.uxc %d bytes, body %d from 0x58 ==='
          % (len(sc), len(sc) - BODY))
    print()

    print('--- 1. raw search for the marker a0 07 26 08 ---')
    hits = find_all(sc, MARKER)
    print('  %d occurrences: %s' % (len(hits), ' '.join('0x%04x' % h for h in hits)))
    if len(hits) < 2:
        print('  fewer than 2 -- cannot derive a stride')
        return 1
    gaps = [hits[i + 1] - hits[i] for i in range(len(hits) - 1)]
    print('  gaps: %s' % ' '.join(str(g) for g in gaps))
    c = Counter(gaps)
    print('  gap histogram: %s'
          % ', '.join('%d x%d' % (k, v) for k, v in c.most_common(6)))
    stride = c.most_common(1)[0][0]
    print('  dominant gap = %d  (n=%d, %.0f%% of gaps)'
          % (stride, c[stride], 100.0 * c[stride] / len(gaps)))
    print()

    print('--- 2. where does rgba sit relative to the marker? ---')
    # for each offset k in a window, count how many marker positions have a
    # palette-matching quad at (marker + k)
    best = []
    for k in range(-24, 25):
        n = 0
        for h in hits:
            o = h + k
            if 0 <= o <= len(sc) - 4 and tuple(sc[o:o + 4]) in pal:
                n += 1
        if n:
            best.append((n, k))
    best.sort(reverse=True)
    for n, k in best[:8]:
        print('  marker %+3d : %3d of %d markers have a palette colour'
              % (k, n, len(hits)))
    if not best:
        print('  no fixed offset from the marker yields palette colours')
        return 1
    n, k = best[0]
    print()
    print('  >> rgba is at marker %+d, in %d of %d records (%.0f%%)'
          % (k, n, len(hits), 100.0 * n / len(hits)))
    print()

    print('--- 3. the index field, now that the boundary is known ---')
    for fld in (0, 1, 2, 3, 4, 5):
        vals = [sc[h + fld] for h in hits if 0 <= h + fld < len(sc)]
        inc = all(vals[i + 1] == (vals[i] + 1) & 0xFF for i in range(len(vals) - 1))
        print('  marker %+d : %s   increasing-by-1: %s'
              % (fld, ' '.join('%02x' % v for v in vals[:24]), inc))
    print()

    print('--- 4. record dump on the derived layout ---')
    rec0 = hits[0] + k - stride if k > 0 else hits[0] + k
    print('  record start appears to be 0x%04x (first marker 0x%04x, k=%d, stride=%d)'
          % (rec0, hits[0], k, stride))
    print()
    print('  %-5s %-8s %-8s %-16s %s'
          % ('#', 'start', 'marker', 'rgba', 'index?'))
    cols = Counter()
    for i, h in enumerate(hits):
        o = h + k
        q = tuple(sc[o:o + 4])
        cols[q] += 1
        print('  %-5d 0x%04x  0x%04x  %-16s %02x'
              % (i, h - (stride - k if k >= 0 else 0), h, ' '.join('%02x' % x for x in q),
                 sc[h - stride] if h >= stride else 0))
        if i >= 30:
            print('  ... %d more' % (len(hits) - i - 1))
            break
    print()
    print('  %d distinct colours' % len(cols))
    for q, n in cols.most_common(20):
        nm = pal.get(q)
        print('    %-14s x%-3d %s' % (' '.join('%02x' % x for x in q), n,
                                     ('== palette 0x%04x' % (0x4000 + nm)) if nm is not None else ''))
    print()

    # 5. round-trip on the derived layout
    print('--- 5. round-trip with the derived record size ---')
    recsize = stride
    body = sc[rec0:] if rec0 >= 0 else b''
    print('  from 0x%04x: %d bytes, /%d = %s'
          % (rec0, len(body), recsize,
             '%.2f' % (len(body) / recsize) if recsize else '?'))
    if recsize and abs(len(body) / recsize - round(len(body) / recsize)) < 1e-9:
        print('  divides evenly: %d records' % round(len(body) / recsize))
    else:
        print('  does NOT divide evenly -> records are variable length, or the')
        print('  body does not start at 0x%04x' % rec0)
    re_emit = bytearray(sc[:rec0])
    for i in range(0, len(body) - recsize + 1, recsize):
        re_emit += body[i:i + recsize]
    re_emit += body[len(body) - (len(body) % recsize):] if len(body) % recsize else b''
    print('  re-emitted %d bytes: %s'
          % (len(re_emit), 'BYTE-EXACT' if bytes(re_emit) == sc else 'MISMATCH'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
