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


@needs_dump
def test_tbh_entries_are_doubled(data):
    """TBH resolves `base + 2*entry`.  A x1 base lands inside the table.

    The tbh at 0x317028 switches on ctx[0] (the capture mode) in ten cases.  With
    the x2 every case target matches the address rizin labels; with x1, ctx[0]=5
    resolves to 0x317036, which is inside the table itself.
    """
    tbh = 0x317028
    assert offsets.is_tbh(hw(data, tbh), hw(data, tbh + 2)) == (3, 1)
    base = tbh + 4
    entries = [hw(data, base + 2 * i) for i in range(10)]
    tgts = offsets.tbh_targets(tbh, entries)
    # the x2 answers rizin's case labels exactly
    assert tgts[5] == 0x317040
    assert tgts[6] == 0x317044
    assert tgts[7] == 0x31704A
    assert tgts[8] == 0x317050
    # and the x1 answer is self-evidently wrong
    naive = [base + e for e in entries]
    assert any(base <= t < base + 20 for t in naive)
    assert not any(base <= t < base + 20 for t in tgts)


@needs_dump
def test_capture_mode_field_is_ctx_0_not_ctx_90(data):
    """The mode the gates test is ctx[0x00]; ctx+0x90 is a different selector.

    ctx+0x90 feeds the 34-way per-mode *limit* resolver (fcn.00316ef8), while the
    capture mode is read as `ldr r3, [r5]` at 0x317022 and dispatched by the tbh at
    0x317028.  Conflating the two is what produced the earlier wrong premise.
    """
    # fcn.00316ef8 reads ctx+0x90 and bounds it to 0x21 -> a 34-way tbb
    assert offsets.ldr_str_offset(hw(data, 0x316EFE), hw(data, 0x316F00)) == \
        ("ldr", 0, 0, 0x90)
    # fcn.00316fd0 reads ctx[0x00] and range-checks it against 9
    assert hw(data, 0x317022) == 0x682B          # ldr r3, [r5]
    assert hw(data, 0x317024) == 0x2B09          # cmp r3, 9
    assert (hw(data, 0x317026) & 0xFF00) == 0xD800   # bhi <default>


@needs_dump
def test_mode_helper_returns_only_zero_or_nine(data):
    """fcn.00864566 is `return (v == 9) ? 9 : 0`.

    It is the only source of a computed mode, and its result becomes both ctx[0]
    and r4.  So the `mov r4, r0` route cannot supply 5 -- which is why r4 == 5 is
    only reachable via ctx+0xc8.
    """
    assert hw(data, 0x86456A) == 0x2809           # cmp r0, 9
    assert hw(data, 0x86456C) == 0xBF0C           # ite eq
    assert hw(data, 0x86456E) == 0x2009           # moveq r0, 9
    assert hw(data, 0x864570) == 0x2000           # movne r0, 0
    assert hw(data, 0x864572) == 0x4770           # bx lr


@needs_dump
def test_no_literal_five_is_written_to_r4(data):
    """None of the 19 literal assignments in fcn.00316fd0 puts 5 in r4."""
    lits = set()
    for o in range(0x316FD0, 0x3172C0, 2):
        v = hw(data, o)
        if (v & 0xFF00) == 0x2400 and ((v >> 8) & 7) == 4:
            lits.add(v & 0xFF)
    assert 5 not in lits
    assert lits <= {0, 1, 6, 8, 9, 0x18, 0x1A, 0x1B, 0x1C}
    assert len(lits) >= 7


# ------------------------------------------------- the write-only sink flag

def _published_va_literals(data, base, lo, hi):
    """File offsets in [lo,hi) whose runtime VA appears as a 32-bit literal."""
    out = set()
    for o in range(0, len(data) - 4, 4):
        v = int.from_bytes(data[o:o + 4], "little")
        if lo <= (v & ~1) - base < hi:
            out.add((v & ~1) - base)
    return out


@needs_dump
def test_mshot_sink_flag_is_write_only(data):
    """0xf59a58 is set seven times and read never -- which retires the flag patch.

    The flag chain is ctx+0x10c -> fcn.0039eb6c -> fcn.003a25fc -> this byte, and
    nothing consumes it.  Checked three ways, with a neighbour that *is* consumed
    as the control so a negative result means something.
    """
    base = 0x635C6000
    sink, neighbour = 0x0F59A58, 0x0F59A5E
    tbl = offsets.resolve_pc_globals(data, window=24)

    # 1. PC-relative references: the sink has only its own setter, the neighbour
    #    only its getter
    assert len(tbl.get(sink, [])) == 1
    assert tbl[sink][0][0] == 0x03A25FC
    assert len(tbl.get(neighbour, [])) == 1
    assert tbl[neighbour][0][0] == 0x03A2608

    # 2. published runtime-VA literals: the neighbour has one, the sink has none
    pub = _published_va_literals(data, base, 0x0F59A50, 0x0F59B80)
    assert neighbour in pub
    assert sink not in pub
    assert len(pub) > 100            # the rest of the table is routinely published

    # 3. the accessor at 0x3a25fc stores a byte; the one at 0x3a2608 does not
    assert _accessor_target(data, 0x03A25FC) == sink
    assert _accessor_target(data, 0x03A2608) == neighbour
    assert _accessor_stores_byte(data, 0x03A25FC)
    assert not _accessor_stores_byte(data, 0x03A2608)


def _accessor_target(data, at):
    """Resolve `ldr rX,[lit]; add rX,pc` at `at` to the address it yields."""
    rd, imm = offsets.is_ldr_pc(hw(data, at))
    assert rd is not None, hex(at)
    lit = at + 4 + imm
    val = int.from_bytes(data[lit:lit + 4], "little")
    for k in range(1, 8):
        p = at + 2 * k
        if offsets.is_add_pc(hw(data, p)) == rd:
            return val + (p + 4)
    raise AssertionError(f"no add r{rd},pc after 0x{at:x}")


def _accessor_stores_byte(data, at):
    """Does the accessor at `at` store a byte before returning?

    The scan must stop at the accessor's `bx lr`: the literal pool immediately
    follows, and a data word there can carry the 0x7xxx pattern that looks like
    `strb`.  Without that bound a plain getter reports a store.
    """
    rd, _imm = offsets.is_ldr_pc(hw(data, at))
    for k in range(1, 8):
        p = at + 2 * k
        h = hw(data, p)
        if (h & 0xFF00) == 0x4700:        # bx lr -- accessor is over
            return False
        if (h & 0xFE00) == 0xBD00:        # pop {.., pc}
            return False
        if offsets.is_add_pc(h) == rd:
            for q in range(p + 2, min(p + 12, len(data) - 2), 2):
                if (hw(data, q) & 0xFF00) == 0x4700:
                    return False
                if (hw(data, q) & 0xF800) == 0x7000:
                    return True
            return False
    return False


@needs_dump
def test_motion_shot_stages_are_referenced(data):
    """The pipeline is live code, which is why the flag was the wrong target."""
    from retool.xrefs import refs_to
    for s in (b"Stage_Motionshot.cpp",
              b"Stage_MotionShot_Analysis",
              b"Stage_Rcv_DistResize_MotionShotMiniYc"):
        i = data.find(s + b"\x00")
        assert i > 0, s
        refs = {r["ldr"] for r in refs_to(data, i, span=0)}
        assert refs, f"{s.decode()} has no code reference"


@needs_dump
def test_stage_code_calls_the_live_sa_func_dispatcher(data):
    """0x334f48 calls the dispatcher; 0x334f50 loads the MOTIONSHOT_start error."""
    t = offsets.bl_target(hw(data, 0x334F48), hw(data, 0x334F4A), 0x334F48)
    assert t == 0x056D50C
    lit = 0x335170
    rd, imm = offsets.is_ldr_pc(hw(data, 0x334F50))
    assert rd is not None and 0x334F50 + 4 + imm == lit
    name = data[lit:lit + 200].split(b"\x00")[0]
    # the literal at 0x335170 is a PC-relative delta, so resolve it first
    delta = int.from_bytes(data[lit:lit + 4], "little")
    tgt = delta + (0x334F54 + 4)
    blob = data[tgt:tgt + 200].split(b"\x00")[0]
    assert b"sa_func_MOTIONSHOT_start" in blob, blob
