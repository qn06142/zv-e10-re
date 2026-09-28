"""Find the uxc resource loader, and read the one .uxc literal in the firmware.

Why hunt the loader rather than perfect the record layout
--------------------------------------------------------
uxc_widget_rec.py showed the widget records are TLV chains, not a fixed
stride, so the colour field's exact offset needs more work than it is worth
right now.  The higher-value target is the code that opens these files,
because it answers two questions at once:

  Q2  does the engine really resolve colour ids against color_cmn.uxc, or
      does it inline colours per widget?  A disassembly of the loader shows
      whether the 0x4000-range id is used as a table index.

  Q5  where does it look?  If the path is built by concatenating a base
      directory from .rodata, the base string is right there in the dump, and
      "would an SD-card copy ever be read" is answered by reading code
      instead of by burning a camera session experimenting.

Why the names are absent from the firmware
-----------------------------------------
The obvious search for b'color_cmn.uxc' and b'/usr/share/app' in av-cam.bin
and fdat_decrypted.bin found nothing.  That is not evidence the loader does
not exist.  global.xdb contains the filenames, so a loader can iterate the
directory table and never embed a literal.  The anchors worth trying instead:

  * b'global.xdb'  -- the one filename a loader must open by name
  * b'fontlist.dat'
  * the 3-byte magics as immediates: 'uxc' = 0x63757875, 'uxb' = 0x62757875,
    'uxa' = 0x61757875
  * the .uxc literal found at 0x090f52fd in fdat_decrypted.bin

Arm caveats already paid for on this codebase: symbol/function addresses
carry the Thumb bit; PC-relative string refs need thumb.pcrel_strrefs.  This
pass is byte/magic search plus a read of the literal's neighbourhood, which
needs none of that.
"""
import re
import struct
from pathlib import Path

ROOT = Path(r'D:\02_Development_And_Projects\pmca-re\dumps')

MAGICS = {
    0x63757875: 'uxc',
    0x62757875: 'uxb',
    0x61757875: 'uxa',
    0x00000007: None,   # too common, tracked separately
}

NAMES = [b'global.xdb', b'fontlist.dat', b'color_cmn', b'style_cmn',
         b'usr/share/app', b'share/app', b'.uxc', b'.uxb', b'.uxa',
         b'uxc', b'uxengine', b'UxEngine', b'UXENGINE']


def neighbourhood(buf, off, before=48, after=96):
    lo = max(0, off - before)
    hi = min(len(buf), off + after)
    ch = buf[lo:hi]
    out = []
    for o in range(0, len(ch), 16):
        row = ch[o:o + 16]
        txt = ''.join(chr(c) if 32 <= c < 127 else '.' for c in row)
        out.append('    %08x  %-47s |%s|'
                   % (lo + o, ' '.join('%02x' % c for c in row), txt))
    return '\n'.join(out)


def scan(buf, name):
    print('=' * 74)
    print('=== %s  (%d bytes) ===' % (name, len(buf)))
    print('=' * 74)

    print('-- filename / path literals --')
    for n in NAMES:
        hits = []
        s = 0
        while True:
            i = buf.find(n, s)
            if i < 0:
                break
            hits.append(i)
            s = i + 1
            if len(hits) > 40:
                break
        if hits:
            print('  %-16s %3d hit(s)  %s'
                  % (n.decode('latin1'), len(hits),
                     ' '.join('0x%08x' % h for h in hits[:10])))

    print('-- container magics as little-endian u32 immediates --')
    for pat, tag in MAGICS.items():
        if tag is None:
            continue
        b = struct.pack('<I', pat)
        hits = []
        s = 0
        while True:
            i = buf.find(b, s)
            if i < 0:
                break
            # only count it as a candidate if it is 4-aligned, which is what
            # a compiler would emit for a .word constant
            if i % 4 == 0:
                hits.append(i)
            s = i + 1
            if len(hits) > 200:
                break
        print('  %-6s 0x%08x  %4d 4-aligned hit(s)  %s'
              % (tag, pat, len(hits), ' '.join('0x%08x' % h for h in hits[:10])))

    print('-- "*.uxc"-shaped literals, in context --')
    for m in re.finditer(rb'[\x20-\x7e]{3,60}', buf):
        s = m.group()
        if b'.uxc' in s or b'.uxb' in s or b'.xdb' in s:
            print('    @0x%08x  %r' % (m.start(), s.decode('latin1')))


def main():
    for p in ('av-cam.bin.bak', 'fdat_decrypted.bin'):
        scan((ROOT / p).read_bytes(), p)
        print()

    # read the neighbourhood of the .uxc literal in fdat
    buf = (ROOT / 'fdat_decrypted.bin').read_bytes()
    i = buf.find(b'.uxc')
    while i >= 0:
        print('--- context of .uxc at 0x%08x ---' % i)
        print(neighbourhood(buf, i))
        print()
        i = buf.find(b'.uxc', i + 1)
        if i > 0x090f6000:
            break

    # how many .uxc literals overall, and are they in a table?
    allh = [m.start() for m in re.finditer(rb'\.uxc', buf)]
    print('=== %d .uxc byte-sequences in fdat ===' % len(allh))
    if len(allh) > 1:
        print('  first 20: %s' % ' '.join('0x%08x' % h for h in allh[:20]))
        gaps = [allh[i + 1] - allh[i] for i in range(len(allh) - 1)]
        from collections import Counter
        c = Counter(gaps)
        print('  gap histogram: %s'
              % ', '.join('%d x%d' % (k, v) for k, v in c.most_common(8)))


if __name__ == '__main__':
    main()
