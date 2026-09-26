"""PC-relative data cross-references for av-cam.bin.

rizin's `axt` returns nothing for this image (verified even against known
strings), so references are resolved directly.

THE TRAP THIS MODULE EXISTS TO AVOID
------------------------------------
A Thumb compiler materialises a data address as

    ldr  rX, [pc, #imm]      ; literal pool slot
    add  rX, pc              ; effective address = pool_value + PC

so the pool holds a PC-relative DELTA, not an address.  A delta looks exactly
like a pointer: it is a plausible 32-bit value, and it often has bit 0 set
(looking like a Thumb function pointer).  Reading pool values as addresses
produces confident, wrong conclusions -- in this investigation it produced two:
a "video mode descriptor table" and a "handler vtable" that were both deltas
to unrelated strings.  Always resolve deltas before interpreting.

Two further traps, both hit during this work:

* An unbounded distance between the `ldr` and the `add` that consumes it
  fabricates references.  `add rX, pc` is also used for ordinary address
  arithmetic, and a distant one reuses a stale pool slot.  The bogus targets
  look precisely like hardware register addresses (odd low bits, one per
  page), which is how a fake "MMIO map" got published.  MAX_LDR_ADD_GAP bounds it.
* An `add rX, pc` preceded by a load from a non-literal source (a struct
  field, a computed pointer) has no literal pool at all, and any nearby match
  is spurious.  A *negative* result is therefore also weak evidence: this
  module has essentially no out-of-image references, which means it never names
  hardware addresses rather than that the scan failed.
"""
from __future__ import annotations

import struct
from array import array
from pathlib import Path

# Thumb encodings
_LDR_T1 = 0x4800   # 0100 1 000 Rt imm8      ldr Rt, [pc, #imm8*4]
_LDR_T3_LO = 0xF85F   # 1111 1000 0101 1111    ldr.w Rt, [pc, #imm12]
_LDR_T3_HI = 0xF89F   # ... with U=1
_ADD_PC = 0x4478   # 0100 0100 0111 1 Rd      add Rd, pc

# Maximum byte distance between a `ldr rX,[pc]` and the `add rX, pc` that
# consumes it.  Compilers emit them adjacent; anything further apart is a
# different instruction that happens to reuse the register.
MAX_LDR_ADD_GAP = 12


def _is_add_pc(hw: int) -> int | None:
    """Return Rd if `hw` is `add Rd, pc`, else None."""
    if (hw & 0xFFF8) == _ADD_PC:
        return hw & 0x7
    return None


def iter_references(data: bytes):
    """Yield (ldr_addr, add_addr, pool_slot, target) for every PC-relative ref.

    All addresses are BYTE addresses.  The halfword array is indexed by
    halfword, so every slot/PC computation must use `i * 2`; getting that
    wrong yields plausible-looking but entirely wrong targets (it did, once --
    the pool slots came out around 0x47b98 instead of 0x8f6c8).
    """
    n = len(data) // 2
    arr = array("H")
    arr.frombytes(data[: n * 2])
    last_ldr: dict[int, tuple[int, int]] = {}   # reg -> (ldr addr, pool addr)
    for i in range(n - 2):
        hw = arr[i]
        a = i * 2
        if (hw & 0xF800) == _LDR_T1:
            last_ldr[(hw >> 8) & 0x7] = (a, ((a + 4) & ~3) + (hw & 0xFF) * 4)
            continue
        if (hw & 0xFF7F) == _LDR_T3_LO or (hw & 0xFF7F) == _LDR_T3_HI:
            base = (a + 4) & ~3
            imm12 = hw & 0xFFF
            slot = base + imm12 if (hw >> 7) & 1 else base - imm12
            last_ldr[(hw >> 12) & 0xF] = (a, slot)
            continue
        r = _is_add_pc(hw)
        if r is not None:
            prev = last_ldr.get(r)
            # The ldr and the add must be adjacent.  Without this window a
            # distant `add rX, pc` reuses a stale pool slot and fabricates
            # thousands of bogus "references" -- which then look exactly like
            # hardware register addresses.
            if prev is not None and (a - prev[0]) <= MAX_LDR_ADD_GAP:
                ldr_a, slot = prev
                if 0 <= slot <= len(data) - 4:
                    pc = (a + 4) & ~3
                    tgt = int.from_bytes(data[slot:slot + 4], "little") + pc
                    yield (ldr_a, a, slot, tgt)


def read_cstring(data: bytes, off: int, maxlen: int = 120) -> str | None:
    """Whole C string containing `off` (reads back to the previous NUL)."""
    if not (0 <= off < len(data)):
        return None
    start = off
    while start > 0 and data[start - 1] != 0:
        start -= 1
        if off - start > maxlen:
            return None
    end = data.find(b"\x00", start, start + maxlen)
    if end <= start:
        return None
    b = data[start:end]
    if not all(32 <= c < 127 for c in b):
        return None
    return b.decode("ascii")


def refs_to(data: bytes, target: int, span: int = 0) -> list[dict]:
    """Every reference whose resolved target falls in [target, target+span]."""
    out = []
    for ldr_a, add_a, slot, tgt in iter_references(data):
        if span and not (target <= tgt < target + span):
            continue
        if not span and tgt != target:
            continue
        out.append({
            "ldr": ldr_a, "add": add_a, "pool": slot, "target": tgt,
            "string": read_cstring(data, tgt),
        })
    return out


def page_histogram(data: bytes) -> dict[int, int]:
    """Count references landing on each 4 KB page -- shows which data is live."""
    hist: dict[int, int] = {}
    for _, _, _, tgt in iter_references(data):
        if 0 <= tgt < len(data):
            p = tgt & ~0xFFF
            hist[p] = hist.get(p, 0) + 1
    return hist
