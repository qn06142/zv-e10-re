"""Tests for retool.offsets -- the decoders, against av-cam.bin itself.

Every assertion below is anchored to a real instruction in dumps/av-cam.bin whose
disassembly is known, rather than to a hand-derived expectation.  That matters
because three of these decoders were got wrong at least once during the RE and the
wrong version agreed with itself.

The image-dependent tests skip if the dump is absent, so the suite still runs in a
checkout without dumps/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from retool import offsets  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DUMP = ROOT / "dumps" / "av-cam.bin"
needs_dump = pytest.mark.skipif(not DUMP.is_file(), reason="av-cam.bin not present")


@pytest.fixture(scope="module")
def data() -> bytes:
    if not DUMP.is_file():
        pytest.skip("av-cam.bin not present")
    return DUMP.read_bytes()


def hw(data: bytes, off: int) -> int:
    return data[off] | (data[off + 1] << 8)


# ---------------------------------------------------------------- pure decoders

def test_ldr_str_imm12_form():
    # 0xf8d5 0x310c = ldr.w r3, [r5, #0x10c]   (av-cam 0x317128)
    assert offsets.ldr_str_offset(0xF8D5, 0x310C) == ("ldr", 5, 3, 0x10C)


def test_ldr_str_offset_above_0xff_is_plain_imm12():
    """The trap that hid ctx+0x10c for a whole round.

    0x317128 is `ldr.w r3, [r5, #0x10c]`, encoded as hw2=0x310C -- bit 11 clear,
    i.e. the plain imm12 form with imm12 = 0x10C.  An earlier sweep identified T2
    with `(hw2 & 0x0F00) == 0`, but imm12's bit 8 sits inside that mask, so every
    access with an offset >= 0x100 was dropped and the field looked untouched.
    """
    hw1, hw2 = 0xF8D5, 0x310C
    assert hw2 & 0x0800 == 0, "this is the T2/imm12 form, not the scaled one"
    assert hw2 & 0x0F00 != 0, "so the 0x0F00 mask would have rejected it"
    assert offsets.ldr_str_offset(hw1, hw2) == ("ldr", 5, 3, 0x10C)


def test_ldr_str_store():
    # 0xf8c5 0x310c = str.w r3, [r5, #0x10c]   (av-cam 0x317140)
    assert offsets.ldr_str_offset(0xF8C5, 0x310C) == ("str", 5, 3, 0x10C)


def test_ldr_str_t3_t4_are_declined_not_guessed():
    """The imm8-scaled forms are refused rather than decoded.

    Their size field sits in hw1[5:4], which is part of T2's fixed pattern, and
    this image has no confirmed T3/T4 access to calibrate against.  Returning a
    plausible-but-unverified offset is worse than returning nothing.
    """
    for hw2 in (0x0800 | 0x0400 | 0x10, 0x0C00 | 0x0200 | 0x40,
                0x0800 | 0x0600 | 0x08):
        assert offsets.ldr_str_offset(0xF8D0, hw2) is None
        assert offsets.ldr_str_offset(0xF8C0, hw2) is None


def test_branch_cond_is_bits_11_8():
    # 0xd007 -> beq. Reading the condition from bits[15:12] yields 0xD ("le") and
    # makes the disassembler look wrong when it is not.
    cond, target = offsets.branch_target(0xD007, 0x317132)
    assert cond == "eq"
    assert target == 0x317144


def test_branch_bne_target():
    cond, target = offsets.branch_target(0xD109, 0x31712E)
    assert cond == "ne"
    assert target == 0x317144


def test_branch_unconditional_is_al():
    cond, _ = offsets.branch_target(0xE007, 0x317132)
    assert cond == "al"


def test_add_pc_register_in_bits_2_0():
    # 0x4478 = add r0,pc ; 0x447a = add r2,pc ; 0x447b = add r3,pc.
    # Rd is bits [2:0]: 0x447B & 0xF == 0xB, not 3.
    assert offsets.is_add_pc(0x4478) == 0
    assert offsets.is_add_pc(0x447A) == 2
    assert offsets.is_add_pc(0x447B) == 3


def test_add_pc_rejects_wrong_mask():
    # 0x44F0 was the mask tried first; it must not match a real add rX, pc
    assert offsets.is_add_pc(0x44F0) is None


def test_ldr_pc_literal_address():
    rd, imm = offsets.is_ldr_pc(0x4B01)      # ldr r3, [pc, #4]
    assert rd == 3 and imm == 4


def test_movw_movt():
    # 0xF241 0x0300 -> movw r3, #0x1000
    # imm4=1, i=0, imm3=0, imm8=0x00 => imm16 = 0x1000 ; Rd = bits[11:8] = 3
    assert offsets.movw_movt(0xF241, 0x0300) == ("movw", 3, 0x1000)
    assert offsets.movw_movt(0xF2C1, 0x0300) == ("movt", 3, 0x1000)


# ------------------------------------------------------------- image-anchored

@needs_dump
def test_validator_bytes_decode_as_documented(data):
    """The three instructions quoted in avcam_re/MOTION_SHOT.md."""
    assert offsets.ldr_str_offset(hw(data, 0x317128), hw(data, 0x31712A)) == \
        ("ldr", 5, 3, 0x10C)
    cond, tgt = offsets.branch_target(hw(data, 0x31712E), 0x31712E)
    assert (cond, tgt) == ("ne", 0x317144)
    cond, tgt = offsets.branch_target(hw(data, 0x317132), 0x317132)
    assert (cond, tgt) == ("eq", 0x317144)


@needs_dump
def test_constructor_zeroes_the_mshot_flag(data):
    """0x7f4fa is `movs r1, #0`, the byte patch B changes."""
    assert hw(data, 0x7F4FA) == 0x2100
    # ...and it feeds both +0x10c and +0x114, which is patch B's side effect
    assert offsets.ldr_str_offset(hw(data, 0x7F502), hw(data, 0x7F504)) == \
        ("str", 3, 1, 0x10C)
    assert offsets.ldr_str_offset(hw(data, 0x7F506), hw(data, 0x7F508)) == \
        ("str", 3, 1, 0x114)


@needs_dump
def test_arming_site_writes_one(data):
    """0x7fc6aa..0x7fc6b0 -- the only site that sets ctx+0x10c to 1."""
    assert hw(data, 0x7FC6AA) == 0x2201          # movs r2, #1
    assert offsets.ldr_str_offset(hw(data, 0x7FC6B0), hw(data, 0x7FC6B2)) == \
        ("str", 4, 2, 0x10C)
    rows = list(offsets.constant_stores(data, 0x10C))
    ones = [r for r in rows if r[3] == 1]
    assert 0x7FC6B0 in [r[0] for r in ones]
    assert len(ones) == 2, f"expected 2 literal-1 stores, got {len(ones)}"


@needs_dump
def test_nearest_def_beats_nearest_matching_immediate(data):
    """The rule that exposed the constructor as a false arming site.

    `movs r1, 1` at 0x7f4f0 is followed by `movs r1, 0` at 0x7f4fa before the
    store at 0x7f502, so the propagated value must be 0, not 1.
    """
    assert hw(data, 0x7F4F0) == 0x2101
    assert hw(data, 0x7F4FA) == 0x2100
    nd = offsets.nearest_def(data, 0x7F502, 1)
    assert nd is not None
    assert nd[0] == 0x7F4FA and nd[1] == 0


@needs_dump
def test_consumer_branch_is_bne_over_the_call(data):
    """fcn.0039eb6c site 0: bne skips bl fcn.003a25fc when the flag is not 1."""
    assert offsets.ldr_str_offset(hw(data, 0x39EE48), hw(data, 0x39EE4A)) == \
        ("ldr", 3, 0, 0x10C)
    cond, tgt = offsets.branch_target(hw(data, 0x39EE4E), 0x39EE4E)
    assert cond == "ne"


@needs_dump
def test_pc_global_resolver_finds_the_sink_global(data):
    """0xf59a58 has exactly one reference, and it is the write."""
    table = offsets.resolve_pc_globals(data)
    assert 0x0F59A58 in table
    assert len(table[0x0F59A58]) == 1
    ldr_off, add_off, _rd = table[0x0F59A58][0]
    assert ldr_off == 0x03A25FC and add_off == 0x03A25FE
    # the resolver must be resolving a real space, not a couple of sites
    assert len(table) > 10000


@needs_dump
def test_resolver_total_is_plausible(data):
    table = offsets.resolve_pc_globals(data)
    total = sum(len(v) for v in table.values())
    assert 50000 < total < 200000


@needs_dump
def test_vtable_address_has_no_movw_movt_pair(data):
    """RcFill's address point is never synthesised -> no constructor."""
    vt = 0x0FC7714 + 4
    va = vt + 0x635C6000
    assert offsets.find_const_pairs(data, va) == []
    # a sibling that *is* constructed, for contrast
    sib = (0x0FC7850 + 4) + 0x635C6000
    assert isinstance(offsets.find_const_pairs(data, sib), list)
