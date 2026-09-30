"""Settle the palette route's blocker: which partitions can actually be written?

The open question from 05-formats.md is whether /usr/share/app is
writable.  It has been unanswered because the only way to answer it was a live
`mount`, and every session has been consumed by the USB wedge instead.  But
F: has the raw flash images, so the question can be answered offline.

What is on the card
-------------------
  RE_DUMP/nflasha1..nflasha23.img, nflashaB0/B1.img   raw partitions
  RE_DUMP/TREES/*.tgz                                  extracted trees

From up.sh, pulled off the card this session:

    mount -t vfat /dev/nflasha1 -o posix_attr,noatime,nodiratime,shortname=mixed ...

so nflasha1 is a vfat partition and is mounted read-write in the updater's own
path.  change_mode.sh writes /setting/mode/dmode and /setting/mode/preload with
plain `echo >`, so nflasha2 (= /setting) is definitively writable -- it is how
the camera changes its own boot mode.

The root filesystem, holding /usr/share/app, is a different question.  If it is
one of the nflash partitions as a read-only romfs/squashfs-style image, no
amount of staging on the card will help, because global.xdb shows the engine
opens resources by absolute /usr/share/app path rather than searching.

So: identify the filesystem type of every nflash image, and find which one
holds /usr/share.  This decides the route before we spend a session.

Method
------
Squashfs magic 'hsqs' (or 'sqsh', 'qshs' for byte-swapped), romfs magic
'-rom1fs-', JFFS2 magic 0x1985 little/big endian, ubi 'UBI#', cramfs
0x28cd3d45, ext 'ext2/3/4' at 0x438.  Raw nflash on this device also appeared
as ext4 in the /proc/iomem notes, so both are checked.  Filesystem type tells
us writability directly: squashfs and romfs are read-only by construction, ext
and vfat are not.
"""
import hashlib
import re
import struct
from pathlib import Path

CARD = Path(r'F:\RE_DUMP')

MAGICS = [
    (b'hsqs', 'squashfs  (READ-ONLY by construction)'),
    (b'sqsh', 'squashfs  (byte-swapped, READ-ONLY)'),
    (b'qshs', 'squashfs  (byte-swapped, READ-ONLY)'),
    (b'-rom1fs-', 'romfs     (READ-ONLY by construction)'),
    (b'UBI#', 'UBI       (writable, wear-levelled)'),
    (b'\x45\x3d\xcd\x28', 'cramfs   (READ-ONLY)'),
    (b'\x85\x19', 'jffs2    (writable, in-place, endian?)'),
    (b'\x19\x85', 'jffs2    (writable, in-place, swapped)'),
    (b'\x53\xef', 'ext2/3/4 (writable)'),
    (b'MSDOS', 'vfat      (writable)'),
    (b'NTFS', 'ntfs      (writable)'),
    (b'\xeb\x3c\x90', 'FAT boot sector (writable)'),
    (b'\xeb\x58\x90', 'FAT32 boot sector (writable)'),
    (b'\xeb\x52\x90', 'exFAT boot sector (writable)'),
]


def probe(path):
    size = path.stat().st_size
    with path.open('rb') as f:
        head = f.read(0x20000)
    found = []
    for magic, name in MAGICS:
        i = head.find(magic)
        if i >= 0:
            found.append((i, name))
    found.sort()
    return size, found


def deep_probe(path, limit=64 * 1024 * 1024):
    """Search the whole image (up to limit) for any magic, at 512-byte stride."""
    hits = {}
    with path.open('rb') as f:
        off = 0
        while off < min(limit, path.stat().st_size):
            f.seek(off)
            chunk = f.read(1 << 20)
            if not chunk:
                break
            for magic, name in MAGICS:
                if magic in hits:
                    continue
                i = chunk.find(magic)
                if i >= 0:
                    hits[magic] = (off + i, name)
            off += (1 << 20) - 16
    return hits


def squashfs_super(b):
    """If this is squashfs, the superblock is big-endian; read the fs size."""
    if b[:4] != b'hsqs':
        return None
    (ino,) = struct.unpack_from('>I', b, 0)
    (bytes_used,) = struct.unpack_from('>I', b, 0x2c)
    (blk_count,) = struct.unpack_from('>I', b, 0x34)
    return dict(ino=ino, bytes_used=bytes_used, blocks=blk_count)


def main():
    print('=== %s ===' % CARD)
    print()
    print('%-20s %12s  %s' % ('partition', 'size', 'filesystem at offset 0'))
    print('-' * 78)
    results = {}
    for p in sorted(CARD.glob('nflasha*.img')):
        size, found = probe(p)
        desc = '; '.join('%s @0x%05x' % (n, o) for o, n in found) or \
            '(no known magic in first 128 KB)'
        results[p.name] = (size, found)
        print('%-20s %12d  %s' % (p.name, size, desc))

    print()
    print('=== deeper scan: any fs magic anywhere in the first 64 MB ===')
    for p in sorted(CARD.glob('nflasha*.img')):
        hits = deep_probe(p)
        if hits:
            for magic, (o, n) in sorted(hits.items(), key=lambda kv: kv[1][0]):
                print('  %-18s %-40s @0x%08x' % (p.name, n, o))
        else:
            print('  %-18s (none found)' % p.name)

    # the partitions we care about, in depth
    print()
    print('=== squashfs superblock detail, if any ===')
    for p in sorted(CARD.glob('nflasha*.img')):
        with p.open('rb') as f:
            head = f.read(0x10000)
        s = squashfs_super(head)
        if s:
            print('  %-18s %s' % (p.name, s))

    print()
    print('=== which partition is the root fs holding /usr/share? ===')
    # nflasha3 was seen as 50 MB and system.tgz holds av-cam.bin (17 MB);
    # nflasha5 is 60 MB and the fdat/firmware lives there.
    # /usr/share alone is 41 MB of tgz, so a partition holding it must be
    # larger than that.  Report the candidates by size.
    for p in sorted(CARD.glob('nflasha*.img'), key=lambda x: -x.stat().st_size):
        print('  %-18s %8.1f MB' % (p.name, p.stat().st_size / 1048576))

    # sanity: do the extracted trees' md5s match the recorded ones?
    print()
    print('=== cross-check: does any image contain the uxc magic? ===')
    for p in sorted(CARD.glob('nflasha*.img')):
        data = p.read_bytes()
        c = data.count(b'uxc\x07\x00\x00\x00\x00\x08\x00')
        if c:
            print('  %-18s %d uxc-container signature(s)' % (p.name, c))
        c2 = data.count(b'color_cmn.uxc')
        if c2:
            print('  %-18s %d literal color_cmn.uxc' % (p.name, c2))


if __name__ == '__main__':
    main()
