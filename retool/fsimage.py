"""Read an ext2/3/4 image and extract files, with no external tooling.

There is no WSL, debugfs, 7z or e2fsprogs on this Windows box, and the ZV-E10's
`/usr` partition images are not filesystem images anyway: nflasha15.img carries a
plausible ext2 superblock at 0x400 but a whole-image scan finds zero ext2
dirent tables. The camera reaches that data through a flash translation layer, so
the on-flash bytes are raw file contents at flash-block-aligned offsets.

That is why the capture path here is "find the file magic, not walk the tree":
carve-by-magic works on both a real ext2 image and a raw flash dump, and needs no
superblock to be trustworthy.

Usage:
    python fsimage.py info   <image>
    python fsimage.py carve  <image> <outdir> [--magic HEX] [--min N]
    python fsimage.py verify <image> <file> <offset>
"""
from __future__ import annotations

import argparse
import hashlib
import re
import struct
import sys
from collections import Counter
from pathlib import Path

# Signatures worth carving out of a camera flash dump, longest/most specific first.
MAGICS: list[tuple[bytes, str, str]] = [
    (b"\x7fELF", "elf", "ARM ELF"),
    (b"hsqs", "squashfs", "SquashFS"),
    (b"\x45\x3d\xcd\x28", "cramfs", "CramFS (note: weak, 4 bytes)"),
    (b"\x1f\x8b", "gz", "gzip"),
    (b"BZh", "bz2", "bzip2"),
    (b"\xfd7zXZ\x00", "xz", "xz"),
    (b"PK\x03\x04", "zip", "zip"),
    (b"ustar", "tar", "tar"),
    (b"SQLite format 3\x00", "sqlite", "SQLite"),
    (b"ORIL", "oril", "Sony ORIL container"),
    (b"UDTRFIRM", "fdat", "Sony UDTRFIRM"),
    (b"\x27\x05\x19\x56", "uimage", "U-Boot uImage"),
    (b"\xd0\x0d\xfe\xed", "fdt", "flattened device tree"),
]


def entropy(b: bytes) -> float:
    if not b:
        return 0.0
    import math
    c = Counter(b)
    n = len(b)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def describe(data: bytes, off: int) -> tuple[int, str, str] | None:
    """If an ELF starts at `off`, return (length, kind, detail)."""
    if off + 52 > len(data):
        return None
    if data[off + 4] != 1 or data[off + 5] != 1:
        return None
    e_type = struct.unpack_from("<H", data, off + 16)[0]
    e_machine = struct.unpack_from("<H", data, off + 18)[0]
    if e_machine != 0x28 or e_type not in (2, 3):
        return None
    shoff = struct.unpack_from("<I", data, off + 32)[0]
    shent, shnum = struct.unpack_from("<HH", data, off + 46)
    phoff = struct.unpack_from("<I", data, off + 28)[0]
    phent, phnum = struct.unpack_from("<HH", data, off + 42)
    end = 0
    if shoff and shnum and shnum < 8192 and shent == 40:
        end = shoff + shent * shnum
    for i in range(min(phnum, 64)):
        po = off + phoff + i * phent
        if po + 32 > len(data):
            break
        if struct.unpack_from("<I", data, po)[0] == 1:      # PT_LOAD
            p_off = struct.unpack_from("<I", data, po + 4)[0]
            p_fsz = struct.unpack_from("<I", data, po + 16)[0]
            end = max(end, p_off + p_fsz)
    if not end or end > len(data) - off:
        return None
    return end, "elf", "ET_%s" % ("EXEC" if e_type == 2 else "DYN")


def cmd_info(a: argparse.Namespace) -> int:
    d = Path(a.image).read_bytes()
    print(f"{a.image}: {len(d):,} bytes")
    c = Counter(d)
    print("  distinct byte values : %d" % len(c))
    print("  top byte             : 0x%02X (%.1f%%)" % (
        c.most_common(1)[0][0], 100 * c.most_common(1)[0][1] / len(d)))
    print("  entropy              : %.2f bits/byte" % entropy(d))
    # ext2 superblock, correctly located at 1024
    if len(d) > 1024 + 0x3A:
        magic = struct.unpack_from("<H", d, 1024 + 0x38)[0]
        if magic == 0xEF53:
            inodes = struct.unpack_from("<I", d, 1024 + 0x00)[0]
            print("  ext2 superblock      : magic 0xEF53, %d inodes" % inodes)
        else:
            print("  ext2 superblock      : none at 0x438 (0x%04X)" % magic)
    # any dirent table at all?
    BS = 1024
    found = 0
    for blk in range(0, min(len(d) // BS, 4096)):
        b = d[blk * BS:(blk + 1) * BS]
        i, r, nl, ft = struct.unpack_from("<IHBB", b, 0)
        if 2 <= nl <= 20 and b[8:8 + nl] == b".":
            found += 1
    print("  dirent tables in first 4MB : %d %s"
          % (found, "(looks like a real fs)" if found else "(not a filesystem image)"))
    return 0


def cmd_carve(a: argparse.Namespace) -> int:
    d = Path(a.image).read_bytes()
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    pats = MAGICS
    if a.magic:
        raw = bytes.fromhex(a.magic)
        pats = [(raw, "custom", "user-specified")]
    total = 0
    for magic, ext, label in pats:
        p = 0
        n = 0
        while True:
            i = d.find(magic, p)
            if i < 0:
                break
            p = i + 1
            if magic == b"\x7fELF":
                got = describe(d, i)
                if not got:
                    continue
                length, _, detail = got
            else:
                length = min(64 * 1024 * 1024, len(d) - i)
                detail = label
            if length < a.min:
                continue
            fn = out / ("%08x_%s.%s" % (i, ext, ext))
            fn.write_bytes(d[i:i + length])
            n += 1
            total += length
        if n:
            print("  %-10s %-28s %4d file(s)" % (ext, label, n))
    print("carved into %s (%s bytes)" % (out, f"{total:,}"))
    return 0


def cmd_verify(a: argparse.Namespace) -> int:
    d = Path(a.image).read_bytes()
    off = int(a.offset, 0)
    blob = d[off:off + int(a.size, 0)] if a.size else d[off:]
    h = hashlib.sha256(blob).hexdigest()
    print("offset %s  %d bytes" % (a.offset, len(blob)))
    print("sha256 %s" % h)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("info"); i.add_argument("image"); i.set_defaults(fn=cmd_info)
    c = sub.add_parser("carve"); c.add_argument("image"); c.add_argument("outdir")
    c.add_argument("--magic"); c.add_argument("--min", type=int, default=64)
    c.set_defaults(fn=cmd_carve)
    v = sub.add_parser("verify"); v.add_argument("image"); v.add_argument("file")
    v.add_argument("offset"); v.add_argument("--size")
    v.set_defaults(fn=cmd_verify)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
