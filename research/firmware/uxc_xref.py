"""Cross-reference the decoded palette against the screens, and decode the rest.

Three questions, all answerable offline from the 12-file tar:

  Q1  Do the view*.uxc screens actually reference the palette ids 0x4000-0x4022?
      This is the positive control for the whole colour_cmn.uxc decode.  If no
      screen file contains a 0x4000-range word, then either the ids mean
      something else, or the screens inherit colour from somewhere else, and
      recolouring the palette would change nothing visible.  A negative here
      kills the approach, so it must be tested rather than assumed.

  Q2  What are the other .uxb containers, and do they share the uxc body shape?
      style.uxb / lang.uxb have stream version 9 and u32 offset tables.  If
      they use the same 8-byte record stride, the format is one thing and not
      three, and the rest of the resource set becomes readable too.

  Q3  What does global.xdb actually index, and does it name absolute paths?
      It is 12,252 bytes of u32 with ~200 resource filenames.  If it stores a
      directory or a search path, that bears on the open question of where the
      engine looks for color_cmn.uxc -- i.e. whether an SD-card copy would
      ever be read.
"""
import re
import struct
import tarfile
from pathlib import Path

TAR = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\ui.tar')
APP = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\app')
HDR_UXC = 0x58
REC = 8
ID_BASE = 0x4000
ID_MAX = 0x4022
UXB = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\app')


def load():
    t = tarfile.open(TAR)
    out = {}
    for m in t.getmembers():
        out[m.name] = t.extractfile(m).read()
    return out


def hdr(b):
    magic = b[:3].decode('latin1')
    ver = b[3]
    stream = struct.unpack_from('<H', b, 8)[0]
    w1 = struct.unpack_from('<H', b, 10)[0]
    w2 = struct.unpack_from('<H', b, 12)[0]
    return magic, ver, stream, w1, w2


def q1_palette_refs(d):
    print('=' * 78)
    print('Q1  do the screens reference palette ids 0x%04x-0x%04x?'
          % (ID_BASE, ID_MAX))
    print('=' * 78)
    names = sorted(d)
    hit = 0
    for n in names:
        b = d[n]
        found = {}
        for o in range(0, len(b) - 1, 2):
            v = struct.unpack_from('<H', b, o)[0]
            if ID_BASE <= v <= ID_MAX:
                found.setdefault(v, []).append(o)
        # also at odd alignment, in case records are not 2-aligned
        for o in range(1, len(b) - 1, 2):
            v = struct.unpack_from('<H', b, o)[0]
            if ID_BASE <= v <= ID_MAX:
                found.setdefault(v, []).append(o)
        if found:
            hit += 1
            print('  %-24s %s' % (n, ' '.join(
                '0x%04x@%s' % (v, ','.join(hex(x) for x in sorted(os)[:4]))
                for v, os in sorted(found.items()))))
    print()
    print('  %d of %d files contain a palette-range word' % (hit, len(names)))
    if hit == 0:
        print('  NEGATIVE: no screen references the palette ids.')
        print('  The decode of color_cmn.uxc may still be right, but the')
        print('  screens would not be consuming it this way.')
    return hit


def q2_uxb(d):
    print()
    print('=' * 78)
    print('Q2  the .uxb containers: same 8-byte record stride?')
    print('=' * 78)
    for n in ('style.uxb', 'lang.uxb'):
        b = d[n]
        magic, ver, stream, w1, w2 = hdr(b)
        print()
        print('  %-14s %d bytes  magic %s ver %d stream %d  hdrw %04x %04x'
              % (n, len(b), magic, ver, stream, w1, w2))
        # u32 offset table from 0x10, as global.xdb does
        nw = (len(b) - 0x10) // 4
        offs = [struct.unpack_from('<I', b, 0x10 + 4 * i)[0] for i in range(nw)]
        sane = [o for o in offs if o < len(b)]
        first = offs[:12]
        print('    u32 from 0x10: %d words, %d in range' % (len(offs), len(sane)))
        print('    first: %s' % ' '.join('%08x' % o for o in first))
        d_ = [offs[i + 1] - offs[i] for i in range(len(offs) - 1)]
        d_ = [x for x in d_ if x > 0]
        if d_:
            from collections import Counter
            c = Counter(d_)
            print('    stride histogram: %s'
                  % ', '.join('%d x%d' % (k, v) for k, v in c.most_common(6)))
        runs = [(m.start(), m.group().decode('latin1'))
                for m in re.finditer(rb'[\x20-\x7e]{4,}', b)]
        if runs:
            print('    %d printable runs, first 8:' % len(runs))
            for o, t in runs[:8]:
                print('      0x%04x  %s' % (o, t[:60]))


def q3_xdb(d):
    print()
    print('=' * 78)
    print('Q3  global.xdb: what does the u32 table index?')
    print('=' * 78)
    b = d['global.xdb']
    magic, ver, stream, w1, w2 = hdr(b)
    print('  %d bytes  magic %s ver %d stream %d  hdrw %04x %04x'
          % (len(b), magic, ver, stream, w1, w2))
    nw = (len(b) - 0x10) // 4
    offs = [struct.unpack_from('<I', b, 0x10 + 4 * i)[0] for i in range(nw)]
    print('  u32 from 0x10: %d words' % nw)
    print('  first 16: %s' % ' '.join('%08x' % o for o in offs[:16]))
    d_ = [offs[i + 1] - offs[i] for i in range(len(offs) - 1)]
    d_ = [x for x in d_ if x > 0]
    from collections import Counter
    c = Counter(d_)
    print('  stride histogram: %s'
          % ', '.join('%d x%d' % (k, v) for k, v in c.most_common(8)))
    # where do the filename strings start, and what precedes them
    runs = [(m.start(), m.group().decode('latin1'))
            for m in re.finditer(rb'[\x20-\x7e]{6,}\.ux[a-z]', b)]
    print('  %d .ux? filename strings' % len(runs))
    if runs:
        print('  first string at 0x%04x' % runs[0][0])
        lo = max(0, runs[0][0] - 48)
        for o in range(lo, runs[0][0] + 16, 16):
            ch = b[o:o + 16]
            print('    %06x  %-47s |%s|'
                  % (o, ' '.join('%02x' % c2 for c2 in ch),
                     ''.join(chr(c2) if 32 <= c2 < 127 else '.' for c2 in ch)))
    # any absolute paths?
    for pat in (b'/usr/share/app', b'//', b'PATH', b'DIR'):
        print('  %-14r occurrences: %d' % (pat, b.count(pat)))


def q4_view_bodies(d):
    print()
    print('=' * 78)
    print('Q4  the tiny view*.uxc screens, fully')
    print('=' * 78)
    for n in sorted(k for k in d if k.startswith('view') or k == 'color_cmn.uxc'):
        b = d[n]
        magic, ver, stream, w1, w2 = hdr(b)
        nrec = (len(b) - HDR_UXC) // REC if len(b) > HDR_UXC else 0
        print()
        print('  %-24s %d bytes  w1 %04x w2 %04x  body %d B = %d x8'
              % (n, len(b), w1, w2, len(b) - HDR_UXC, nrec))
        for i in range(min(nrec, 6)):
            o = HDR_UXC + i * REC
            print('      rec %2d @0x%04x  %s' % (
                i, o,
                ' '.join('%02x' % c for c in b[o:o + REC])))


def main():
    d = load()
    print('=== ui.tar members ===')
    for k in sorted(d):
        print('  %-24s %7d' % (k, len(d[k])))
    print()
    print('=== headers, all files ===')
    for k in sorted(d):
        magic, ver, stream, w1, w2 = hdr(d[k])
        print('  %-24s magic %-4s ver %d stream %d  hdrw %04x %04x'
              % (k, magic, ver, stream, w1, w2))
    print()
    n = q1_palette_refs(d)
    q2_uxb(d)
    q3_xdb(d)
    q4_view_bodies(d)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
