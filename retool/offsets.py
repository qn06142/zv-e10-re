"""Thumb-2 offset/branch decoding and PC-relative global resolution.

These are the decoders that were hand-rolled repeatedly while reverse engineering
av-cam.bin, each one costing a round trip because the obvious reading is wrong.
They are collected here so the offsets quoted in avcam_re/*.md are reproducible
from committed tooling rather than from throwaway scripts.

Every decoder below was checked against a known instruction in av-cam.bin rather
than derived from the ARM ARM alone, and the traps are recorded at each one.

Traps encoded here (each one already cost a round):

* LDR/STR (immediate) has three offset forms, and the way you tell T2 from T3/T4
  decides whether you see a field at all. **T2 is selected by ``hw2 & 0x0800 == 0``,
  not by ``hw2 & 0x0F00 == 0``** -- the immediate is a full 12 bits, so its bit 8
  lives inside the 0x0F00 mask. Using 0x0F00 silently drops every access with an
  offset >= 0x100; that is why ctx+0x10c first appeared to have no accesses at all
  when it in fact has 123. Its encoding is the plain imm12 form (0x310C: Rt=3,
  imm12=0x10C), *not* the imm8-scaled form.
* Thumb-1 ``B<cond>`` keeps the condition in **bits [11:8]**, not [15:12].
  ``b eq`` is 0xD0xx, ``b ne`` is 0xD1xx, unconditional ``b`` is 0xE0xx. Reading
  the condition from the top nibble yields 0xD ("LE") and suggests the disassembler
  is wrong when it is not.
* ``add rX, pc`` is ``0x4478 | Rd`` with **Rd in bits [2:0]** -- the base already
  has bit 3 set, so ``0x447B & 0xF == 0xB``, not 3.
* A PC-relative global's delta is relative to the *using* instruction, so
  searching the image for one delta value finds only that one site. Resolve every
  ``ldr rX,[pc]`` / ``add rX,pc`` pair instead.
"""

from __future__ import annotations

import struct
from collections import defaultdict

# Thumb-1 B<cond> condition field is bits [11:8].
COND = {
    0x0: "eq", 0x1: "ne", 0x2: "cs", 0x3: "cc",
    0x4: "mi", 0x5: "pl", 0x6: "vs", 0x7: "vc",
    0x8: "hi", 0x9: "ls", 0xA: "ge", 0xB: "lt",
    0xC: "gt", 0xD: "le", 0xE: "al",
}

ADD_PC_BASE = 0x4478        # add rX, pc ; Rd occupies bits [2:0]
ADD_PC_MASK = 0xFFF8


def ldr_str_offset(hw1: int, hw2: int) -> tuple[str, int, int, int] | None:
    """Decode a 32-bit LDR/STR (immediate).  Returns (kind, rn, rt, offset).

    kind is "ldr" or "str".  offset is signed.  Returns None if the pair is not
    one of the immediate forms -- register-offset and post-indexed forms are
    deliberately out of scope.

    T2 (plain imm12, offsets 0..4095) is identified by **bit 11 clear**.  Do not    widen that test to 0x0F00: the immediate occupies all of hw2[11:0], so its
    bit 8 is part of the offset, not a flag.  Every LDR/STR of a field at 0x100 or
    above vanishes under the wider mask.

    The T3/T4 forms (bit 11 set, imm8 scaled by access size) are **declined, not
    decoded**.  Their size field lives in hw1[5:4], which is part of T2's fixed
    pattern, and this image contains no confirmed T3/T4 access to calibrate
    against -- so any scale table here would be a guess dressed as a decoder, and
    a wrong offset is far worse than an absent one.  Add them only alongside a real
    example from the binary.
    """
    if (hw1 & 0xFFF0) == 0xF8C0:
        kind = "str"
    elif (hw1 & 0xFFF0) == 0xF8D0:
        kind = "ldr"
    else:
        return None
    rn = hw1 & 0xF
    rt = (hw2 >> 12) & 0xF
    if (hw2 & 0x0800) == 0:
        return kind, rn, rt, hw2 & 0xFFF
    return None            # T3/T4: uncalibrated, see docstring


def branch_target(hw1: int, addr: int) -> tuple[str, int] | None:
    """Decode a Thumb-1 B<cond> / unconditional B.  Returns (cond_name, target).

    Only the 16-bit forms.  For 32-bit instructions use bl_target().
    """
    if (hw1 & 0xF000) == 0xD000 and (hw1 & 0x0F00) != 0x0F00:
        cond = COND.get((hw1 >> 8) & 0xF, f"n{(hw1 >> 8) & 0xF:x}")
        off = (hw1 & 0xFF) << 1
        if off & 0x200:
            off -= 0x400
        return cond, addr + 4 + off
    if (hw1 & 0xF800) == 0xE000:
        return "al", addr + 4 + 0            # caller must add the imm11 field
    return None


def is_add_pc(hw1: int) -> int | None:
    """If hw1 is `add rX, pc`, return X; else None."""
    if (hw1 & ADD_PC_MASK) == ADD_PC_BASE:
        return hw1 & 0x7
    return None


def is_ldr_pc(hw1: int) -> tuple[int, int] | None:
    """If hw1 is `ldr rX, [pc, #imm]`, return (X, imm_bytes); else None."""
    if (hw1 & 0xF800) == 0x4800:
        return (hw1 >> 8) & 7, (hw1 & 0xFF) * 4
    return None


def movw_movt(hw1: int, hw2: int) -> tuple[str, int, int] | None:
    """Decode MOVW/MOVT.  Returns (kind, rd, imm16) or None."""
    for kind, pat in (("movw", 0xF240), ("movt", 0xF2C0)):
        if (hw1 & 0xFBF0) == pat:
            i = (hw1 >> 10) & 1
            imm4 = hw1 & 0xF
            imm3 = (hw2 >> 12) & 7
            imm8 = hw2 & 0xFF
            rd = (hw2 >> 8) & 0xF
            return kind, rd, (imm4 << 12) | (i << 11) | (imm3 << 8) | imm8
    return None


def bl_target(hw1: int, hw2: int, addr: int) -> int | None:
    """Decode a 32-bit BL.  J1/J2 live in the **second** halfword."""
    if (hw1 & 0xF800) != 0xF000 or (hw2 & 0xD000) != 0xD000:
        return None
    s = (hw1 >> 10) & 1
    imm10 = hw1 & 0x3FF
    j1 = (hw2 >> 13) & 1
    j2 = (hw2 >> 11) & 1
    imm11 = hw2 & 0x7FF
    i1 = (~(j1 ^ s)) & 1
    i2 = (~(j2 ^ s)) & 1
    imm = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
    if s:
        imm -= 1 << 25
    return addr + 4 + imm


# --------------------------------------------------------------------------
# data-driven sweeps
# --------------------------------------------------------------------------

def iter_halfwords(data: bytes):
    for off in range(0, len(data) - 1, 2):
        yield off, data[off] | (data[off + 1] << 8)


def offset_accesses(data: bytes, target: int, kind: str | None = None):
    """Every LDR/STR (immediate) touching `target`, as (off, kind, rn, rt, off)."""
    for off, hw1 in iter_halfwords(data):
        if (hw1 & 0xFFF0) not in (0xF8C0, 0xF8D0):
            continue
        if off + 4 > len(data):
            break
        hw2 = data[off + 2] | (data[off + 3] << 8)
        r = ldr_str_offset(hw1, hw2)
        if not r:
            continue
        k, rn, rt, o = r
        if o == target and (kind is None or k == kind):
            yield off, k, rn, rt, o


def nearest_def(data: bytes, use_off: int, reg: int, span: int = 64):
    """Nearest preceding *definition* of `reg`.  Returns (off, value, how).

    The correct rule is nearest-definition-of-any-value, not "nearest assignment of
    the value we happen to want".  Matching only the wanted immediate made a
    constructor look like an arming site, because an intervening `movs rX, 0`
    silently overrode an earlier `movs rX, 1`.

    Recognises movs rd,#imm8 and mov.w rd,#imm16 as literal definitions; a load or
    a register move yields value None (unknown).
    """
    for p in range(use_off - 2, max(-1, use_off - span), -2):
        if p < 0:
            break
        hw1 = data[p] | (data[p + 1] << 8)
        if (hw1 & 0xF800) == 0x2000 and ((hw1 >> 8) & 7) == reg and (hw1 & 0x80) == 0:
            return p, hw1 & 0xFF, "movs"
        if p + 4 <= len(data):
            hw2 = data[p + 2] | (data[p + 3] << 8)
            if (hw1 & 0xFFF0) == 0xF04F and ((hw2 >> 12) & 0xF) == reg \
                    and (hw2 & 0xF000) == 0:
                return p, hw2 & 0x0FFF, "mov.w"
            if (hw1 & 0xFFC0) == 0xEA80 and (hw2 & 0xF000) == 0 \
                    and ((hw2 >> 8) & 0xF) == reg:
                return p, None, "mov rm"
        if (hw1 & 0xF800) == 0x6800 and ((hw1 >> 8) & 0xF) == reg:
            return p, None, "ldr"
    return None


def constant_stores(data: bytes, target: int):
    """Stores to `target` whose value is a propagated literal.

    Yields (store_off, rn, rt, value, def_off, how).  This is what identified
    0x7fc6b0 as the sole arming site for ctx+0x10c.
    """
    for off, k, rn, rt, _o in offset_accesses(data, target, kind="str"):
        nd = nearest_def(data, off, rt)
        if nd and nd[1] is not None:
            yield off, rn, rt, nd[1], nd[0], nd[2]


def resolve_pc_globals(data: bytes, window: int = 6):
    """Map every PC-relative global address to the pairs that reference it.

    Returns {resolved_file_offset: [(ldr_off, add_off, reg), ...]}.  In av-cam.bin
    this resolves 102,754 pairs into 64,993 distinct globals.

    Pairing is `ldr rX, [pc, #imm]` followed within `window` instructions by
    `add rX, pc`; the resolved address is the literal's value plus the address of
    the *add* plus 4 (Thumb PC is the instruction address + 4).
    """
    ldrs = []
    for off, hw1 in iter_halfwords(data):
        r = is_ldr_pc(hw1)
        if not r:
            continue
        rd, imm = r
        lit = off + 4 + imm
        if lit + 4 <= len(data):
            val = int.from_bytes(data[lit:lit + 4], "little")
            ldrs.append((off, rd, val))
    out = defaultdict(list)
    for off, rd, val in ldrs:
        for k in range(1, window + 1):
            p = off + 2 * k
            if p + 2 > len(data):
                break
            hw = data[p] | (data[p + 1] << 8)
            if is_add_pc(hw) == rd:
                out[val + (p + 4)].append((off, p, rd))
                break
    return out


def find_const_pairs(data: bytes, target: int, window: int = 10):
    """MOVW+MOVT pairs building `target`.  Used to find vtable references."""
    movw, movt = defaultdict(list), defaultdict(list)
    for off, hw1 in iter_halfwords(data):
        if off + 4 > len(data):
            break
        hw2 = data[off + 2] | (data[off + 3] << 8)
        m = movw_movt(hw1, hw2)
        if m:
            (movw if m[0] == "movw" else movt)[m[2]].append((off, m[1]))
    lo, hi = target & 0xFFFF, (target >> 16) & 0xFFFF
    hits = []
    for a, rd in movw.get(lo, ()):
        for b, rd2 in movt.get(hi, ()):
            if rd2 == rd and 0 < b - a <= window * 2 and (b - a) % 2 == 0:
                hits.append((a, b, rd))
    return sorted(hits)
