"""Decode the .uxc UI resource container -- the palette the camera draws itself with.

Why this file matters
--------------------
The objective is a visible, unmistakably-ours effect on the panel, through the
firmware's own legitimate code path.  /usr/share/app is where the UI lives, and
it is resource-driven: ~200 .uxc files named for screens (viewSettingMenu,
viewQuickNavi, ...) plus shared resources.  Two of the shared ones are tiny and
global:

    color_cmn.uxc     312 bytes   the common colour palette
    style_cmn.uxc   1,888 bytes   common style/attribute set
    style.uxb          540 bytes
    fontlist.dat       360 bytes

If the UI renders from a palette in color_cmn.uxc, then altering one entry
recolours real screens the camera itself draws -- an effect that is plainly
ours, needs no new code path, no ioctl, no message id, and no risk of wedging
the display, because the engine already reads the file.  312 bytes is also
small enough to back up and restore byte-exactly.

So the job here is to reverse the container format offline.  Same traps as
before: do not assume a header layout from plausibility, print the raw bytes
first, and distinguish "I decoded it" from "the bytes look like what I hoped".
"""
import re
import struct
import tarfile
from pathlib import Path

TAR = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\ui.tar')
OUT = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\app')
OUT.mkdir(parents=True, exist_ok=True)


def hexdump(b, base=0, width=16, limit=None):
    n = len(b) if limit is None else min(limit, len(b))
    for o in range(0, n, width):
        chunk = b[o:o + width]
        hx = ' '.join('%02x' % c for c in chunk)
        tx = ''.join(chr(c) if 32 <= c < 127 else '.' for c in chunk)
        print('    %06x  %-*s  |%s|' % (base + o, width * 3, hx, tx))


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def analyse(name, b):
    print('=' * 78)
    print('=== %s  %d bytes  magic %s ===' % (name, len(b), b[:16].hex(' ')))
    print('  first 96 bytes:')
    hexdump(b, 0, 16, 96)
    # candidate magic / version
    for m in re.finditer(rb'[A-Za-z][A-Za-z0-9_]{2,15}', b[:64]):
        print('  tag at 0x%02x: %r' % (m.start(), m.group().decode('latin1')))
    # all printable runs
    runs = [(m.start(), m.group().decode('latin1'))
            for m in re.finditer(rb'[\x20-\x7e]{4,}', b)]
    if runs:
        print('  %d printable runs:' % len(runs))
        for o, t in runs[:25]:
            print('    0x%04x  %s' % (o, t[:70]))
    # plausible 32-bit words
    words = [u32(b, o) for o in range(0, len(b) - 3, 4)]
    print('  %d u32 words' % len(words))
    return words


def main():
    t = tarfile.open(TAR)
    members = t.getmembers()
    print('=== ui.tar: %d members ===' % len(members))
    data = {}
    for m in members:
        b = t.extractfile(m).read()
        (OUT / m.name).write_bytes(b)
        data[m.name] = b
        print('  %-26s %7d' % (m.name, len(b)))
    print()

    for name in sorted(data):
        analyse(name, data[name])
        print()

    # focus: color_cmn.uxc
    cb = data.get('color_cmn.uxc')
    if cb:
        print('=' * 78)
        print('=== color_cmn.uxc: hunting an RGB/ARGB table ===')
        print('  full dump (%d bytes):' % len(cb))
        hexdump(cb, 0, 16)
        print()
        # 3-byte runs (RGB) and 4-byte runs (ARGB/RGBA) with plausible values
        for step, label in ((4, 'ARGB/RGBA'), (3, 'RGB')):
            print('  --- as %s triples/quads, aligned at 0 ---' % label)
            for o in range(0, len(cb) - step + 1, step):
                v = cb[o:o + step]
                if all(0 <= c <= 255 for c in v) and (max(v) > 0x20):
                    pass
            break
        # count zero-bytes: a palette of mostly-opaque colours has few zeros
        print('  zero bytes: %d of %d' % (cb.count(0), len(cb)))
        print('  byte histogram (top 12): %s'
              % sorted(range(256), key=lambda x: -cb.count(x))[:12])


if __name__ == '__main__':
    main()
