"""Tests for retool.fsimage -- carving files out of camera flash images.

The behaviour that matters here is negative: a wrong answer must look wrong.
`nflasha15.img` carries a byte-perfect ext2 superblock at 0x400 yet contains no
ext2 directory entries at all, so a tool that trusted the superblock would
happily report a filesystem that isn't there.  These tests pin that distinction
using the real captured image when it is present.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retool import fsimage  # noqa: E402

DUMP = Path(r"F:\RE_DUMP")
N15 = DUMP / "nflasha15.img"
N7 = DUMP / "nflasha7.img"
needs_dump = pytest.mark.skipif(
    not N15.is_file(), reason="nflasha15.img not present (card not attached)")


# ----------------------------------------------------------------- unit ----

def test_elf_extent_uses_section_and_segment_tables(tmp_path):
    """A synthetic ELF: extent must cover both the section table and PT_LOAD."""
    shoff, shnum, shentsize = 0x200, 3, 40
    phoff, phnum, phentsize = 0x40, 1, 32
    buf = bytearray(0x400)
    buf[0:4] = b"\x7fELF"
    buf[4], buf[5] = 1, 1
    struct.pack_into("<H", buf, 16, 3)          # ET_DYN
    struct.pack_into("<H", buf, 18, 0x28)       # ARM
    struct.pack_into("<I", buf, 28, phoff)
    struct.pack_into("<I", buf, 32, shoff)
    struct.pack_into("<HH", buf, 42, phentsize, phnum)
    struct.pack_into("<HH", buf, 46, shentsize, shnum)
    # PT_LOAD covering 0..0x300  (larger than the section table's 0x278)
    struct.pack_into("<I", buf, phoff, 1)
    struct.pack_into("<I", buf, phoff + 4, 0)
    struct.pack_into("<I", buf, phoff + 16, 0x300)
    got = fsimage.describe(bytes(buf), 0)
    assert got is not None
    length, kind, _ = got
    assert kind == "elf"
    assert length == 0x300, "PT_LOAD must win when it is the larger extent"


def test_elf_extent_rejects_non_arm():
    buf = bytearray(0x200)
    buf[0:4] = b"\x7fELF"
    buf[4], buf[5] = 1, 1
    struct.pack_into("<H", buf, 16, 2)
    struct.pack_into("<H", buf, 18, 0x3E)       # x86-64
    assert fsimage.describe(bytes(buf), 0) is None


def test_elf_extent_rejects_absurd_section_counts():
    """A garbage shnum must not be trusted into a huge length."""
    buf = bytearray(0x400)
    buf[0:4] = b"\x7fELF"
    buf[4], buf[5] = 1, 1
    struct.pack_into("<H", buf, 16, 3)
    struct.pack_into("<H", buf, 18, 0x28)
    struct.pack_into("<I", buf, 32, 0x200)      # shoff
    struct.pack_into("<HH", buf, 46, 40, 60000)  # absurd shnum
    struct.pack_into("<HH", buf, 42, 32, 0)
    assert fsimage.describe(bytes(buf), 0) is None


def test_entropy_of_uniform_data_is_zero():
    assert fsimage.entropy(b"\x00" * 4096) == 0.0


def test_entropy_of_uniform_data_is_eight_bits_at_max():
    assert fsimage.entropy(bytes(range(256)) * 16) == pytest.approx(8.0, abs=1e-9)


# ------------------------------------------------------- against the real ----

@needs_dump
def test_nflasha15_has_an_ext2_magic_but_is_not_a_filesystem():
    """The trap this whole tool exists to survive.

    nflasha15.img has a valid-looking ext2 superblock at 0x400, so a naive reader
    would happily treat it as a mountable filesystem.  It is not: the camera sees
    this through a flash translation layer, and the on-flash bytes are raw file
    contents.  Both facts must be reported, not silently reconciled.
    """
    d = N15.read_bytes()
    magic = struct.unpack_from("<H", d, 1024 + 0x38)[0]
    assert magic == 0xEF53, "expected the (coincidental) ext2 magic to be present"

    # ...but there is no root directory anywhere near the start of the image
    BS = 1024
    dirents = 0
    for blk in range(0, min(len(d) // BS, 8192)):
        b = d[blk * BS:(blk + 1) * BS]
        i, r, nl, ft = struct.unpack_from("<IHBB", b, 0)
        if 2 <= nl <= 20 and b[8:8 + nl] == b".":
            dirents += 1
    assert dirents == 0, (
        "found %d dirent blocks -- if this now passes, the image really is a "
        "filesystem and fsimage's carve-by-magic rationale needs revisiting" % dirents)


@needs_dump
def test_nflasha15_carves_230_arm_elfs():
    """Regression anchor: the 2025 /usr capture yielded 230 ELFs, 108.4 MB.

    If this count moves, the capture or the carver changed, and any conclusion
    drawn from "the front end is in elf_05610c00.so" needs rechecking.
    """
    d = N15.read_bytes()
    n = 0
    total = 0
    p = 0
    while True:
        i = d.find(b"\x7fELF", p)
        if i < 0:
            break
        p = i + 1
        got = fsimage.describe(d, i)
        if got:
            n += 1
            total += got[0]
    assert n == 230, "expected 230 ARM ELFs, found %d" % n
    # 108.4 MiB == 113,690,012 bytes.  Compare in bytes against the exact
    # observed total: earlier I wrote 108_000_000..109_000_000, which is a MiB
    # figure compared as if it were bytes, so the bound could never hold.
    assert total == 113_690_012, "total extent moved: %d" % total


@needs_dump
def test_carved_elf_carries_the_camuser_front_end():
    """The single file the whole Motion Shot verdict rests on."""
    d = N15.read_bytes()
    off = d.find(b"\x7fELF", 0x05610000)
    assert 0x05610C00 <= off < 0x05611000, "front-end ELF moved: 0x%x" % off
    got = fsimage.describe(d, off)
    assert got is not None
    length, _, _ = got
    blob = d[off:off + length]
    assert blob.count(b"CamUser") > 400
    assert blob.count(b"ObjRenderer") > 3000
    # Golf Shot has a full mode class; Motion Shot must NOT have one
    assert b"CamModeGolfShotE" in blob
    assert b"CamModeMotionShotE" not in blob
    assert b"SequenceSetMotionShotModeE" in blob
    assert b"SequenceMotionShotPlayStartE" not in blob


@needs_dump
def test_nflasha7_rootfs_is_also_not_a_plain_filesystem():
    if not N7.is_file():
        pytest.skip("nflasha7.img not present")
    d = N7.read_bytes()
    assert struct.unpack_from("<H", d, 1024 + 0x38)[0] == 0xEF53
    BS = 1024
    dirents = 0
    for blk in range(0, min(len(d) // BS, 8192)):
        b = d[blk * BS:(blk + 1) * BS]
        i, r, nl, ft = struct.unpack_from("<IHBB", b, 0)
        if 2 <= nl <= 20 and b[8:8 + nl] == b".":
            dirents += 1
    assert dirents == 0
