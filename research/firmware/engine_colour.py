"""Extract viewUnified*.so and hunt for the colour path in compiled code.

The view format is solved and the colour path is closed on the resource side: no
view property carries a palette id, so if the guides follow 0x400c then the
rendering code must hold the id.  That is testable now, because the code has been
found.

The engine is a family, not a single binary:

    viewUnified2.so   14,284,732    largest non-bitmap ELF in /usr
    viewUnified3.so      941,232
    viewUnified4.so    3,287,604
    viewUnified5.so      749,136
    viewUnified6.so      589,336
    viewUnified7.so      579,944
    viewUnified8.so      283,208

Seven engines, presumably one per screen class.  viewUnified2 is the one that
matters: it is by far the largest, so it has the most code, and the menu and
live-view rendering is where a colour constant would live.

The search, with the null model this project has learned to require:

A palette id in code is a 16-bit or 32-bit immediate.  Searching a 14 MB binary
for a two-byte pattern produces hits by the thousand and they mean nothing on
their own -- the lesson of the byte-pair retraction.  So every candidate is
compared against control ids of the same magnitude and byte shape that are NOT
palette entries.  If 0x400c is enriched relative to its controls, it is
referenced deliberately; if it sits at the control rate, it is not.

Three encodings are searched, because a compiler could emit any of them:
    u16  0x400c        as an immediate operand
    u32  0x0000400c    as a widened constant
    and the whole 0x4000..0x4022 range, to see whether *any* palette id is
    used far more than chance, which is the stronger and more useful test.

The range test is the good one.  If the code indexes the palette, the ids will
appear in a structured way -- probably in a lookup table in .rodata, possibly
one per widget property.  A table of 28 or 35 consecutive ids is unmistakable,
and finding it would also hand over the palette-loading code.

Extraction: the archive is a truncated gzip, so members are read by the
sequential tar reader rather than tarfile.
"""
import gzip
import struct
from collections import Counter
from pathlib import Path

USR = Path(r'F:\RE_DUMP\usr.tgz')
OUT = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\engine')
BLOCK = 512
PAL_LO, PAL_HI = 0x4000, 0x4022
NPAL = PAL_HI - PAL_LO + 1
CONTROLS = [0x4F00, 0x5A00, 0x6B00, 0x7C00, 0x3E00, 0x2D00, 0x8A00, 0x9B00]
TARGET = 0x400C

WANT = ('viewUnified', 'libSysDef.so', 'CautionConfig.so', 'libObj.so',
        'libmpr.so', 'libmprctrl.so', 'libInfraHdmi.so')


def walk(fh):
    """Yield (name, size, data) sequentially, stopping cleanly at damage.

    The archive is a truncated gzip, so the read of the last member's payload
    raises EOFError rather than returning short.  Catching it here means every
    member written before the cut is yielded, instead of aborting the whole
    walk and losing the tail.
    """
    while True:
        try:
            hdr = fh.read(BLOCK)
        except (EOFError, OSError):
            return
        if len(hdr) < BLOCK or hdr == b'\x00' * BLOCK:
            return
        name = hdr[0:100].rstrip(b'\x00').decode('latin1', 'replace')
        try:
            size = int(hdr[124:136].rstrip(b'\x00 ').decode('latin1') or '0', 8)
        except ValueError:
            return
        if size < 0 or size > 200 * 1024 * 1024:
            return
        buf = bytearray()
        left = size
        while left > 0:
            try:
                c = fh.read(min(left, 1 << 20))
            except (EOFError, OSError):
                if buf:
                    yield name, len(buf), bytes(buf)
                return
            if not c:
                if buf:
                    yield name, len(buf), bytes(buf)
                return
            buf += c
            left -= len(c)
        yield name, size, bytes(buf)
        pad = (size + BLOCK - 1) // BLOCK * BLOCK - size
        if pad:
            try:
                fh.read(pad)
            except (EOFError, OSError):
                return


def extract():
    OUT.mkdir(parents=True, exist_ok=True)
    got = []
    with gzip.open(USR, 'rb') as fh:
        for name, size, data in walk(fh):
            base = name.rsplit('/', 1)[-1]
            if any(base.startswith(w) or base == w for w in WANT):
                (OUT / base).write_bytes(data)
                got.append((base, size))
                print('  extracted %-24s %10d' % (base, size))
    return got


def scan(path, label):
    b = path.read_bytes()
    n = len(b)
    print()
    print('--- %s (%d bytes) ---' % (label, n))
    # u16 range test
    tgt16 = 0
    ctl16 = 0
    in_range = Counter()
    for o in range(0, n - 1, 2):
        v = struct.unpack_from('<H', b, o)[0]
        if PAL_LO <= v <= PAL_HI:
            tgt16 += 1
            in_range[v] += 1
        if v in CONTROLS:
            ctl16 += 1
    windows = n // 2
    exp = windows * NPAL / 65536.0
    print('  u16: %d windows, %d in palette range (expect %.1f), %d controls'
          % (windows, tgt16, exp, ctl16))
    if exp > 0:
        print('      palette/expected %.1fx   palette/control %.2fx'
              % (tgt16 / exp, tgt16 / ctl16 if ctl16 else 0))
    # u32
    t32 = b.count(struct.pack('<I', TARGET))
    c32 = sum(b.count(struct.pack('<I', c)) for c in CONTROLS)
    print('  u32 0x%04x: %d   controls: %d' % (TARGET, t32, c32))
    # 4-aligned u16, which is what a .word table would hold
    a16 = 0
    ca16 = 0
    for o in range(0, n - 1, 4):
        v = struct.unpack_from('<H', b, o)[0]
        if PAL_LO <= v <= PAL_HI:
            a16 += 1
        if v in CONTROLS:
            ca16 += 1
    aw = n // 4
    aexp = aw * NPAL / 16384.0
    print('  u16 4-aligned: %d windows, %d in range (expect %.1f), %d controls'
          % (aw, a16, aexp, ca16))
    if aexp > 0:
        print('      palette/expected %.1fx   palette/control %.2fx'
              % (a16 / aexp, a16 / ca16 if ca16 else 0))
    if in_range:
        print('  palette ids present 4-aligned, by value:')
        for v, c in in_range.most_common(12):
            print('      0x%04x  x%d' % (v, c))
    return a16, aexp


def main():
    print('=== extracting the engine family ===')
    got = extract()
    if not got:
        print('  nothing extracted')
        return
    print()
    print('=== palette id search, with a null model ===')
    for base, _s in got:
        p = OUT / base
        if p.exists() and p.stat().st_size > 100000:
            scan(p, base)
    print()
    print('=== a literal string search, cheap and unambiguous ===')
    for base, _s in got:
        b = (OUT / base).read_bytes()
        for pat in (b'color_cmn', b'.uxc', b'uxc', b'style_cmn', b'global.xdb',
                    b'0x400c', b'color', b'palette'):
            n = b.count(pat)
            if n:
                print('  %-24s %-12s x%d' % (base, pat.decode(), n))


if __name__ == '__main__':
    main()
