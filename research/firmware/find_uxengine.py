"""Find the UI engine binary, and look for palette ids compiled into code.

The puzzle
----------
The magenta test proved the framing guides resolve colour through palette entry
0x400c.  But 0x400c appears in exactly ONE view file across all 299
(viewContPbGroup.uxc at 0x0e20).  If the guide lines were drawn by a widget in a
view file, the id would appear in whichever view draws them -- and the guides
show on every screen, including live view, which has no view file of its own.

So the likely explanation is the opposite of what has been assumed: the guide
colour is a compiled-in immediate in the rendering code, and color_cmn.uxc is
simply the palette that code indexes into.  Which means the 228 view files were
the wrong place to look for 0x400c, and the interesting question is what the
engine binary contains.

Where the engine is
-------------------
etc/procs.txt shows 60+ threads named liro-kliro_* and uxengine_res2 appeared in
a process map.  /usr/bin has no candidate -- its 48 files are tools, and the
largest is bsa_server (4.8 MB, Bluetooth).  So the engine is elsewhere: either
in a library, or inside a packed image rather than as a loose file.

The full /usr tree is 91 MB on the card (RE_DUMP/usr.tgz).  This inventories it,
ranks ELF files by size, and searches every one of them for palette-id
immediates.

What to look for
----------------
A palette reference in compiled code appears as a 16-bit or 32-bit immediate:

    0x4c 0x40      u16 0x400c, little-endian, in a .rodata table
    0c 40 00 00    u32 0x0000400c

Both are weak signals on their own -- the u16 in particular will hit by chance
in any large binary.  So the null model is computed: count occurrences of 0x400c
against count of a matched set of random control ids in the same files.  If
0x400c appears more often than its controls do, it is referenced deliberately.

That control is the whole point.  Byte-searching for a two-byte value in a
50 MB binary produces hits by the thousand and they mean nothing on their own.
"""
import re
import struct
import tarfile
from collections import Counter
from pathlib import Path

USR = [
    Path(r'F:\RE_DUMP\usr.tgz'),
    Path(r'F:\RE_DUMP\TREES\usr_share.tgz'),
]
PAL_BASE, PAL_MAX = 0x4000, 0x4022
TARGET = 0x400C

# control ids: same magnitude, same byte pattern family, not real palette entries
CONTROLS = [0x4F00, 0x5A00, 0x6B00, 0x7C00, 0x3E00, 0x2D00]


def pick():
    for p in USR:
        if p.exists():
            try:
                with p.open('rb') as f:
                    f.read(2)
                return p
            except OSError:
                continue
    raise SystemExit('no readable usr archive')


def inventory():
    t = tarfile.open(pick())
    files = [(m.name, m.size) for m in t.getmembers() if m.isfile()]
    print('=== %s: %d files, %.1f MB ==='
          % (pick().name, len(files), sum(s for _n, s in files) / 1048576))
    return t, files


def find_elfs(t, files):
    print()
    print('=== directories ===')
    top = Counter()
    for n, s in files:
        p = n.split('/')
        top['/'.join(p[:2])] += 1
    for d, c in top.most_common(30):
        print('  %-30s %4d files' % (d, c))
    print()
    print('=== largest 30 files, and whether ELF ===')
    elfs = []
    for n, s in sorted(files, key=lambda x: -x[1])[:30]:
        head = t.extractfile(n).read(4) if s else b''
        is_elf = head == b'\x7fELF'
        if is_elf:
            elfs.append((n, s))
        print('  %10d  %-44s %s' % (s, n[:44], 'ELF' if is_elf else ''))
    return elfs


def harvest_elfs(t, files, min_size=2000):
    print()
    print('=== every ELF in the tree, by size ===')
    elfs = []
    for n, s in sorted(files, key=lambda x: -x[1]):
        if s < min_size:
            continue
        try:
            head = t.extractfile(n).read(4)
        except Exception:
            continue
        if head == b'\x7fELF':
            elfs.append((n, s))
    for n, s in elfs[:50]:
        print('  %10d  %s' % (s, n))
    print('  (%d ELFs total >= %d bytes)' % (len(elfs), min_size))
    return elfs


def scan_for_ids(t, elfs, limit=40):
    print()
    print('=== palette ids as immediates in ELF code, with a null model ===')
    print('    (a u16 hit is meaningless on its own; the control columns are the test)')
    print()
    print('  %-40s %10s %7s %7s %7s' % ('file', 'size', '0x400c', 'ctrl', 'mean'))
    hits = []
    for n, s in elfs[:limit]:
        b = t.extractfile(n).read()
        t16 = 0
        pat = struct.pack('<H', TARGET)
        i = 0
        while True:
            i = b.find(pat, i)
            if i < 0:
                break
            t16 += 1
            i += 1
        c = [b.count(struct.pack('<H', x)) for x in CONTROLS]
        mean = sum(c) / len(c) if c else 0
        if t16 or max(c or [0]):
            print('  %-40s %10d %7d %7d %7.1f'
                  % (n.split('/')[-1][:40], s, t16, max(c or [0]), mean))
        if t16 > mean * 2 and t16 >= 4:
            hits.append((t16, mean, n, s))
    print()
    if hits:
        hits.sort(reverse=True)
        print('  >> files where 0x400c is enriched over its controls:')
        for t16, mean, n, s in hits:
            print('     %-40s %d hits vs %.1f mean control (%.1fx)'
                  % (n.split('/')[-1][:40], t16, mean, t16 / mean if mean else 0))
    else:
        print('  no file shows 0x400c enriched over the control ids.')
    return hits


def main():
    t, files = inventory()
    elfs = harvest_elfs(t, files)
    scan_for_ids(t, elfs)


if __name__ == '__main__':
    main()
