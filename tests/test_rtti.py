"""Tests for retool.rtti -- RTTI recovery from a stripped ARM shared object.

The method under test: mangled typeinfo name strings are present in the binary but
unreferenced for most classes, so a class is only "RTTI referenced" if some 32-bit
word in the image resolves, as a virtual address, onto its NUL-terminated name.

Two failure modes are pinned here, both of which produced a wrong answer first:

  * restricting candidate addresses to the EXECUTABLE segment.  The name strings
    live in the read-only DATA segment, so this found 1 hit where the truth is 5
    (and 70 of 442 across the namespace).  A negative produced that way is
    meaningless -- it looks like "dormant" when it is really "not looked at".
  * assuming file offset == virtual address.  The two PT_LOADs here have deltas
    0 and +0x8000, so an address recovered without going through the program
    headers is off by 0x8000 for anything in the second segment.

The image-dependent tests pin the observed split so a regression in either the
decoder or the segment mapping shows up as a changed count.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retool import rtti  # noqa: E402

ELF = ROOT / "dumps" / "camera_2025" / "usr_lib_raw" / "elf_05610c00.so"
needs_elf = pytest.mark.skipif(not ELF.is_file(),
                               reason="carved front-end ELF not present")


# ---------------------------------------------------------------- synthetic --

def _elf(loads, blob):
    """Build a minimal ELF32 with the given PT_LOADs around `blob`."""
    ehsize, phentsize = 52, 32
    phoff = ehsize
    body_off = phoff + phentsize * len(loads)
    d = bytearray(body_off + len(blob))
    d[0:4] = b"\x7fELF"
    d[4], d[5] = 1, 1
    struct.pack_into("<H", d, 16, 3)             # ET_DYN
    struct.pack_into("<H", d, 18, 0x28)          # ARM
    struct.pack_into("<I", d, 28, phoff)
    struct.pack_into("<H", d, 42, phentsize)
    struct.pack_into("<H", d, 44, len(loads))
    for i, (va, fsz, flags) in enumerate(loads):
        o = phoff + i * phentsize
        struct.pack_into("<I", d, o, 1)          # PT_LOAD
        struct.pack_into("<I", d, o + 4, body_off)   # p_offset
        struct.pack_into("<I", d, o + 8, va)         # p_vaddr
        struct.pack_into("<I", d, o + 16, fsz)
        struct.pack_into("<I", d, o + 20, fsz)
        struct.pack_into("<I", d, o + 24, flags)
    d[body_off:] = blob
    return bytes(d)


def test_va_to_file_respects_each_segment_delta():
    """Two segments with different deltas must both map correctly."""
    blob = bytes(0x1000)
    # seg A: va 0 -> off body, delta 0.  seg B: va 0x2000, delta 0x800.
    e = rtti.Elf(_elf([(0, 0x100, 5), (0x2000, 0x100, 6)], blob))
    assert e.va_to_file(0) is not None
    assert e.va_to_file(0x2000) is not None
    # a VA in the gap between the segments must not resolve
    assert e.va_to_file(0x1500) is None


def test_exec_ranges_excludes_data_segment():
    e = rtti.Elf(_elf([(0, 0x100, 5), (0x2000, 0x100, 6)], bytes(0x100)))
    assert e.exec_ranges == [(0, 0x100)]
    assert len(e.all_ranges) == 2, "all_ranges must span both segments"


def test_name_in_data_segment_is_still_found():
    """Regression: candidates must not be restricted to the executable segment.

    A mangled name placed in the SECOND (data) segment must still be reported,
    even though it sits outside exec_ranges.  This is the bug that made the tool
    report 1 RTTI hit where the truth is 70.
    """
    name = b"N7CamUser14CamModeHSMovieE\x00"
    body = 52 + 32 * 2                     # ehsize + 2 program headers
    seg2_file = body                       # p_offset of both loads, per _elf()
    # Lay the name at file offset seg2_file + 0x40, i.e. inside the data segment.
    blob = bytearray(0x100)
    blob[0x40:0x40 + len(name)] = name
    e = rtti.Elf(_elf([(0, 0x40, 5), (0x2000, 0x100, 6)], bytes(blob)))

    name_va = 0x2000 + 0x40                # data segment VA + in-segment offset
    assert not any(a <= name_va < b for a, b in e.exec_ranges), \
        "precondition: the name must lie outside the executable range"

    # Plant a pointer to name_va in the data segment's own bytes.
    d = bytearray(e.d)
    struct.pack_into("<I", d, seg2_file + 0x80, name_va)
    e2 = rtti.Elf(bytes(d))

    hits = rtti.find_rtti_names(e2)
    assert "N7CamUser14CamModeHSMovieE" in hits, (
        "a name living in the data segment must still be found; restricting "
        "candidates to exec_ranges is the bug this test pins")


def test_is_mangled_accepts_type_names_and_rejects_prose():
    assert rtti.is_mangled("N7CamUser14CamModeHSMovieE")
    assert rtti.is_mangled("N11OBJRENDERER31SequenceAppSetGolfShotLayoutCmdE")
    assert not rtti.is_mangled("Motion Shot Video")
    assert not rtti.is_mangled("STRID_FUNC_MOTION_SHOT_VIDEO")
    assert not rtti.is_mangled("ERROR!!! SetMotionShotModeForLiro NON SUPPORTED")


# ------------------------------------------------------------ against the real --

@needs_elf
def test_recovers_70_of_442_camuser_classes():
    """Observed split. A change here means the decoder or mapping regressed."""
    e = rtti.Elf(ELF.read_bytes())
    r = rtti.classify(e, "N7CamUser")
    assert len(r["present"]) == 442, "compiled-in class count moved"
    assert len(r["referenced"]) == 70, "RTTI-referenced count moved: %d" % len(r["referenced"])


@needs_elf
def test_cammode_split_is_five_referenced_eight_string_only():
    e = rtti.Elf(ELF.read_bytes())
    r = rtti.classify(e, "N7CamUser")
    live = {k for k in r["referenced"] if "CamMode" in k}
    assert live == {
        "N7CamUser12CamModeReadyE",
        "N7CamUser12CamModeStillE",
        "N7CamUser14CamModeHSMovieE",
        "N7CamUser15CamModeSHSMovieE",
        "N7CamUser9CamModeEOE",
    }, "CamMode RTTI split changed: %s" % sorted(live)


@needs_elf
def test_golfshot_mixed_and_motionshot_string_only():
    """The load-bearing result, corrected.

    Golf Shot is NOT uniformly dormant: SequenceGolfShotPlayStartE does carry an
    RTTI reference, so its typeinfo is referenced by something polymorphic.  Its
    *mode* class and its capture-start sequence do not.  An earlier scratch pass
    wrongly reported all three as string-only because it searched only VAs below
    0x1400000 and so missed references into the second PT_LOAD.

    Motion Shot's single class has no RTTI reference.

    Asymmetry to keep in mind: an RTTI reference is STRONG evidence of life; its
    absence is WEAK evidence of dormancy, since a class can be reached without
    RTTI.  These assertions are therefore deliberately one-directional.
    """
    e = rtti.Elf(ELF.read_bytes())
    r = rtti.classify(e, "N7CamUser")
    pres, ref = r["present"], r["referenced"]

    for name in ("N7CamUser15CamModeGolfShotE",
                 "N7CamUser25SequenceGolfShotPlayStartE",
                 "N7CamUser28SequenceGolfShotCaptureStartE",
                 "N7CamUser25SequenceSetMotionShotModeE"):
        assert name in pres, "%s should be compiled in" % name

    # the one live Golf Shot class
    assert "N7CamUser25SequenceGolfShotPlayStartE" in ref

    # ...but not its mode class, not its capture sequence, not Motion Shot's
    for name in ("N7CamUser15CamModeGolfShotE",
                 "N7CamUser28SequenceGolfShotCaptureStartE",
                 "N7CamUser25SequenceSetMotionShotModeE"):
        assert name not in ref, "%s unexpectedly gained an RTTI reference" % name


@needs_elf
def test_positive_control_classes_are_referenced():
    """Without these, every 'unreferenced' verdict would be vacuous."""
    e = rtti.Elf(ELF.read_bytes())
    ref = rtti.classify(e, "N7CamUser")["referenced"]
    for name in ("N7CamUser12CamModeStillE",      # stills shoot on this camera
                 "N7CamUser14CamModeHSMovieE",    # high-speed movie mode
                 "N7CamUser9CamModeEOE"):        # end-of-encoding
        assert name in ref, "control %s lost its RTTI reference" % name
