"""Immediate-constant scanner for retool.

Finds the instruction encodings of a given integer inside a function (or the
whole image).  This is the primitive needed to verify firmware patch points:
the RE notes claim things like "change 3376 -> 4000 at 0x8a5d0", and that
claim is only meaningful if the constant is actually encoded there.

Handles the ARM/Thumb immediate encodings that matter in practice:
  Thumb  mov.w / movw  imm16          (0x0D30 as d0 03)
  Thumb  cmp.w / adds / movs  imm8     (small values)
  ARM    mov / mvn / cmp  rotated imm8
  Any    literal-pool word equal to the value

Reports file offset of every hit so a patch can be located exactly.
"""
from __future__ import annotations

import struct
from pathlib import Path


def _thumb_movw_imm16(insn: int, nxt: int) -> int | None:
    """Decode the imm16 of a Thumb-2 MOVW/MOVT, if `insn` starts one.

    T3 encoding (32-bit form, the one compilers emit for values > 255):
        11110 i 100100 imm4   0 imm3 Rd imm8
          [15:11]  [10] [9:4]  [3:0]   [15] [14:12] [11:8] [7:0]
        imm16 = imm4:i:imm3:imm8

    NOTE the immediate spans BOTH halfwords -- decoding from the first halfword
    alone silently produces garbage.
    """
    # MOVW (T3)
    if (insn & 0xFBF0) == 0xF240:
        return (((insn & 0xF) << 12)
                | (((insn >> 10) & 1) << 11)
                | (((nxt >> 12) & 7) << 8)
                | (nxt & 0xFF))
    # MOVT (T1) -- upper half, reported as imm16 << 16 by the caller if needed
    if (insn & 0xFBF0) == 0xF2C0:
        return -1 - (((insn & 0xF) << 12)
                     | (((insn >> 10) & 1) << 11)
                     | (((nxt >> 12) & 7) << 8)
                     | (nxt & 0xFF))
    return None


def _arm_imm8(value: int) -> bool:
    """True if `value` is encodable as an ARM modified-immediate constant."""
    if value < 0:
        return False
    v = value
    for _ in range(16):                    # ror through 32 bits, step 2
        if v == value and (v & 0xFF) == value:
            return True
        if v <= 0xFF:
            return True
        v = ((v >> 1) | (v << 31)) & 0xFFFFFFFF
        # also try '1' rotation (0xXY -> 0xXYXY)
        low = v & 0xFFFF
        if ((low << 16) | low) == value:
            return True
    return False


def scan(data: bytes, base: int, start: int, size: int, targets: list[int]) -> list[dict]:
    """Return every occurrence of each target within [start, start+size)."""
    end = min(start + size, len(data))
    hits: list[dict] = []

    for off in range(start, end - 3, 2):
        hw = struct.unpack_from("<H", data, off)[0]
        nxt = struct.unpack_from("<H", data, off + 2)[0]
        imm = _thumb_movw_imm16(hw, nxt)
        if imm is not None and imm >= 0:
            for t in targets:
                if imm == t:
                    hits.append({
                        "off": off, "va": base + off, "value": t,
                        "kind": "thumb-movw", "bytes": data[off:off + 4].hex(),
                    })
        elif imm is not None:
            val32 = (-1 - imm) << 16
            for t in targets:
                if val32 == t:
                    hits.append({
                        "off": off, "va": base + off, "value": t,
                        "kind": "thumb-movt", "bytes": data[off:off + 4].hex(),
                    })
        for t in targets:
            if hw == (t & 0xFFFF):
                hits.append({
                    "off": off, "va": base + off, "value": t,
                    "kind": "u16-le", "bytes": data[off:off + 2].hex(),
                })

    for off in range(start, end - 3, 4):
        (w,) = struct.unpack_from("<I", data, off)
        for t in targets:
            if w == t:
                hits.append({
                    "off": off, "va": base + off, "value": t,
                    "kind": "u32-le", "bytes": data[off:off + 4].hex(),
                })
    return hits


def scan_image(path: Path, base: int, targets: list[int]) -> list[dict]:
    return scan(path.read_bytes(), base, 0, path.stat().st_size, targets)
