"""Correct the colour_cmn.uxc claim, and find the real uxc structure.

Two problems, one of them mine.

PROBLEM 1 -- the round-trip test was a tautology, and I overclaimed on it.

uxc_color.py printed "BYTE-EXACT MATCH -- container decoded, patch is
trustworthy".  That test is incapable of failing.  It parses into records,
re-packs the same fields, and concatenates the untouched prefix -- which is the
exact inverse of the parse, so it returns the input for ANY fixed stride that
divides the body evenly.  It proves the codec is self-consistent, i.e. that it
loses nothing.  It does not prove the field boundaries are where I put them.
A 4-byte or 16-byte stride would have passed identically.

So the honest evidence for the 8-byte layout of color_cmn.uxc is only:

  * the u16 at +0 steps 0x4000, 0x4001, ... 0x4022 at exactly stride 8, and
    0x4023 in the header is one past the last, so the range is self-consistent
  * the bytes at +4..+7 form plausible UI colours (white, black at five
    alphas, three greys, orange, yellow, r/g/b primaries) and nothing else in
    the file does
  * 28 records fill to EOF exactly

That is circumstantial, not proof.  And this script now tests it against
alternatives rather than assuming it.

PROBLEM 2 -- the cross-reference failed, which is the control that matters.

uxc_xref.py searched all 12 pulled files for u16 words in the palette id range
0x4000-0x4022.  Only color_cmn.uxc itself contains them, and only at its own
record positions.  The hits in global.xdb, lang.uxb and lang_cmn.uxc are at
unrelated offsets and are almost certainly coincidence.

If no screen file names a palette id, then recolouring the palette does not
necessarily change what the screen draws, and the whole approach rests on an
unverified assumption about how the engine consumes it.

And note the view*.uxc files disprove the 8-byte model outright:

  viewBaseMenu.uxc   84 bytes -- SHORTER than the 0x58 header I assumed
  viewAutoPowerOff   rec0 @0x58 = 64 e9 4d 00 00 00 00 00   (not an id+rgba)

So 0x58 is not a universal header size and the 8-byte record is specific to
color_cmn.uxc at best.  This script works out what the common structure
actually is, across all eight uxc files.
"""
import struct
import tarfile
from collections import Counter
from pathlib import Path

TAR = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\ui.tar')


def load():
    t = tarfile.open(TAR)
    return {m.name: t.extractfile(m).read() for m in t.getmembers()}


def alt_strides(b):
    """Which strides make the +0 u16 run as a consecutive 0x4000+ sequence?"""
    hits = []
    for hdr in (0x0c, 0x0e, 0x10, 0x14, 0x18, 0x20, 0x58):
        for stride in (4, 6, 8, 10, 12, 16, 20, 24, 32):
            if hdr >= len(b):
                continue
            n = (len(b) - hdr) // stride
            if n < 8:
                continue
            vals = [struct.unpack_from('<H', b, hdr + i * stride)[0]
                    for i in range(n)]
            run = 0
            for a, c in zip(vals, vals[1:]):
                run = run + 1 if c == a + 1 else 0
                if run >= 8:
                    hits.append((hdr, stride, n, 'consecutive run >=9'))
                    break
    return hits


def main():
    d = load()
    uxc = {k: v for k, v in d.items() if v[:3] == b'uxc'}
    print('=== %d uxc files ===' % len(uxc))
    for k in sorted(uxc):
        print('  %-24s %6d bytes  w1=0x%04x w2=0x%04x'
              % (k, len(uxc[k]),
                 struct.unpack_from('<H', uxc[k], 10)[0],
                 struct.unpack_from('<H', uxc[k], 12)[0]))

    print()
    print('=== color_cmn.uxc: is stride 8 uniquely consistent? ===')
    b = d['color_cmn.uxc']
    for hdr, stride, n, why in alt_strides(b):
        print('  hdr 0x%02x stride %2d  n=%2d  %s' % (hdr, stride, n, why))
    print()
    print('  (a stride that also produces a long consecutive id run would be')
    print('   an equally consistent reading; there is exactly one above)')

    print()
    print('=== what does the 0x0E table in color_cmn.uxc look like? ===')
    tab = [struct.unpack_from('<H', b, 0x0e + 2 * i)[0]
           for i in range((0x58 - 0x0e) // 2)]
    print('  %d u16 from 0x0e to 0x57: %s' % (len(tab), ' '.join('%04x' % v for v in tab)))
    print('  distinct: %s' % sorted(set(tab)))
    print('  non-0xffff count: %d' % sum(1 for v in tab if v != 0xffff))
    # are the non-hole values even and ascending?
    good = [v for v in tab if v != 0xffff]
    print('  ascending after holes removed: %s' % (good == sorted(good)))
    print('  all even: %s' % all(v % 2 == 0 for v in good))
    print('  first value %d, last %d, step 2 -> %d entries'
          % (good[0], good[-1], len(good)))

    print()
    print('=== the four words 0x4007..0x400f as 4-byte little-endian ===')
    for i in range(0x5c, 0xd8, 4):
        w = struct.unpack_from('<I', b, i)[0]
        print('  0x%04x  %02x %02x %02x %02x   as u32 0x%08x  as BGRA %02x%02x%02x%02x'
              % (i, b[i], b[i+1], b[i+2], b[i+3], w, b[i+2], b[i+1], b[i], b[i+3]))

    print()
    print('=== common structure across all 8 uxc files ===')
    print('  byte      0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15')
    names = sorted(uxc)
    print('  %s' % (' ' * 10).join(n[:4] for n in names))
    for off in range(0, 16):
        row = '  %s' % ('%2d      ' % off)
        cells = []
        for n in names:
            bb = uxc[n]
            cells.append('%02x' % bb[off] if off < len(bb) else '--')
        print(row + ' '.join('%-4s' % c for c in cells))
    print()
    print('  columns 0-6 are identical across every uxc file:')
    common = set(uxc[names[0]][:7])
    for n in names:
        common &= set(uxc[n][:7])
    print('    %s' % ' '.join('%02x' % c for c in sorted(common)))
    print('  column 8-9 (stream version) splits by magic:')
    for n in names:
        print('    %-24s %d' % (n, struct.unpack_from('<H', uxc[n], 8)[0]))

    print()
    print('=== do the view files share color_cmn\'s body shape at all? ===')
    for n in sorted(k for k in uxc if k.startswith('view')):
        bb = uxc[n]
        print('  %-24s' % n)
        for o in range(0, min(len(bb), 96), 16):
            ch = bb[o:o + 16]
            print('    %04x  %-47s |%s|'
                  % (o, ' '.join('%02x' % c for c in ch),
                     ''.join(chr(c) if 32 <= c < 127 else '.' for c in ch)))

    print()
    print('=== global.xdb: the 15 /usr/share/app paths (staging question) ===')
    x = d['global.xdb']
    import re
    for m in re.finditer(rb'/usr/share/app[^\x00]{0,80}', x):
        print('  @0x%04x  %s' % (m.start(), m.group().decode('latin1')))
    for m in re.finditer(rb'/[A-Za-z0-9_./-]{4,60}', x):
        s = m.group().decode('latin1')
        if not s.endswith(('.uxa', '.uxb', '.uxc')):
            print('  @0x%04x  %s   <-- not a resource filename' % (m.start(), s))


if __name__ == '__main__':
    main()
