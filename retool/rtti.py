"""Recover RTTI-referenced class names from a stripped, relocation-free ARM .so.

WHY THIS EXISTS
---------------
The ZV-E10's front end (elf_05610c00.so, carved from nflasha15.img) ships with no
.symtab, no .dynsym, no .dynamic and ZERO relocations, and a corrupted section
header table.  The usual construction test -- find a mangled typeinfo name, then
find the word pointing at it -- appears to fail, which previously led to the
conclusion that construction was "unverifiable".

It does not fail.  The name strings are present; they are simply *unreferenced* for
the large majority of classes, because a class only needs a typeinfo when something
polymorphic refers to it.  Scanning every aligned 32-bit word, resolving it as a
virtual address through the program headers, and testing whether a NUL-terminated
mangled name sits there recovers the classes that ARE live.

    PT_LOAD[0]  off 0x00000000  va 0x00000000  R-X   delta 0
    PT_LOAD[1]  off 0x0135dd8c  va 0x01365d8c  RW-   delta +0x8000

The two segments have DIFFERENT file/VA deltas, so address recovery must go through
the program headers, never a bare file offset.  That mismatch produced a false
"never constructed" verdict earlier in this work.

WHAT A HIT MEANS, PRECISELY
---------------------------
  RTTI referenced  -> something polymorphic refers to this typeinfo.  Strong
                      evidence the class participates in a live vtable.
  string only      -> the class is compiled in, but nothing refers to its
                      typeinfo.  Consistent with dormant.  NOT proof of dead: a
                      class can be reached without RTTI, and indirect references
                      or a mis-mapped segment would hide a real one.

So "no RTTI reference" is weaker than "RTTI referenced".  Only 119 of 442 CamUser
names are referenced here, and the reason for that low rate is not established.
Treat the split as a ranking, not a verdict.
"""
from __future__ import annotations

import re
import struct
from collections import defaultdict
from pathlib import Path

# Itanium C++ ABI typeinfo: [0]=own vtable, [1]=name, [2]=base typeinfo.
# We do not rely on this layout -- see find_rtti_names() -- but the mangled-name
# shape test does, and it is stable across Itanium ABIs.
MANGLED = re.compile(rb"^_?Z[\w.]+|\A[NPL][0-9]+")


class Elf:
    """Just enough ELF to map between file offsets and virtual addresses."""

    def __init__(self, data: bytes):
        self.d = data
        if data[:4] != b"\x7fELF":
            raise ValueError("not an ELF")
        if data[4] != 1 or data[5] != 1:
            raise ValueError("not ELF32 LE")
        phoff = struct.unpack_from("<I", data, 28)[0]
        phent, phnum = struct.unpack_from("<HH", data, 42)
        self.loads: list[tuple[int, int, int, int]] = []
        for i in range(phnum):
            o = phoff + i * phent
            if o + 32 > len(data):
                break
            p_type = struct.unpack_from("<I", data, o)[0]
            if p_type != 1:                      # PT_LOAD only
                continue
            off, va = struct.unpack_from("<I", data, o + 4)[0], struct.unpack_from("<I", data, o + 8)[0]
            fsz = struct.unpack_from("<I", data, o + 16)[0]
            flags = struct.unpack_from("<I", data, o + 24)[0]
            self.loads.append((off, va, fsz, flags))
        if not self.loads:
            raise ValueError("no PT_LOAD segments")

    @property
    def exec_ranges(self) -> list[tuple[int, int]]:
        return [(va, va + fsz) for _o, va, fsz, fl in self.loads if fl & 1]

    @property
    def all_ranges(self) -> list[tuple[int, int]]:
        return [(va, va + fsz) for _o, va, fsz, _fl in self.loads]

    def va_to_file(self, va: int) -> int | None:
        for off, v, fsz, _fl in self.loads:
            if v <= va < v + fsz:
                return off + (va - v)
        return None

    def cstr(self, file_off: int, limit: int = 200) -> str | None:
        if not (0 <= file_off < len(self.d)):
            return None
        e = self.d.find(b"\x00", file_off, file_off + limit)
        if e < 0:
            return None
        b = self.d[file_off:e]
        if len(b) < 3 or not all(32 <= c < 127 for c in b):
            return None
        return b.decode("ascii")


def is_mangled(name: str) -> bool:
    """Itanium ABI shape: N<len><Name>E for a type, optionally N/K/V prefixes."""
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\d+[A-Za-z_][A-Za-z0-9_]*E", name)) or \
        bool(re.fullmatch(r"N\d+[A-Za-z_][A-Za-z0-9_]*E", name))


def all_mangled_names(elf: Elf) -> dict[str, int]:
    """Every mangled name string present in the image, -> file offset."""
    out: dict[str, int] = {}
    for m in re.finditer(rb"N\d+[A-Za-z_][A-Za-z0-9_]{2,80}E\x00", elf.d):
        out.setdefault(m.group()[:-1].decode("ascii"), m.start())
    return out


def find_rtti_names(elf: Elf, lo_va: int | None = None,
                    hi_va: int | None = None) -> dict[str, list[int]]:
    """Mangled names that some 32-bit word in the image actually points at.

    A hit is a word whose value, read as a virtual address, lands on a
    NUL-terminated mangled name.

    Candidate addresses must span EVERY PT_LOAD, not just the executable one.  The
    first version of this function restricted them to `exec_ranges` and silently
    found 1 hit instead of 119: the mangled-name strings live in the read-only
    *data* segment (va 0x1365d8c..0x1459320), not in the RX segment, so almost every
    real reference was discarded before it was ever tested.  `exec_ranges` is the
    wrong filter for locating strings -- use it only to decide whether a *code*
    pointer looks plausible.
    """
    ranges = elf.all_ranges
    if lo_va is not None:
        ranges = [(max(a, lo_va), b) for a, b in ranges if b > lo_va]
    if hi_va is not None:
        ranges = [(a, min(b, hi_va)) for a, b in ranges if a < hi_va]
    hits: dict[str, list[int]] = defaultdict(list)
    d = elf.d
    # Precompute the load ranges once; `any(...)` per word is needlessly slow
    # over a 20 MB image.
    lo = min(a for a, _b in ranges)
    hi = max(b for _a, b in ranges)
    for o in range(0, len(d) - 4, 4):
        w = struct.unpack_from("<I", d, o)[0]
        # Only words that fall inside some segment's VA range can be addresses.
        # Do NOT impose an extra absolute floor such as 0x10000: a small or
        # low-mapped image legitimately has names at low VAs, and a hardcoded
        # floor silently drops real references.
        if not (lo <= w < hi):
            continue
        fo = elf.va_to_file(w)
        if fo is None:
            continue
        s = elf.cstr(fo)
        if s and is_mangled(s):
            hits[s].append(o)
    return dict(hits)


def classify(elf: Elf, namespace: str = "N7CamUser") -> dict:
    """Split the namespace's classes into RTTI-referenced vs string-only."""
    present = {}
    for m in re.finditer((namespace + r"\d+[A-Za-z_][A-Za-z0-9_]*E\x00").encode(), elf.d):
        present.setdefault(m.group()[:-1].decode("ascii"), m.start())
    referenced = find_rtti_names(elf)
    live = {k: v for k, v in present.items() if k in referenced}
    dead = {k: v for k, v in present.items() if k not in referenced}
    return {"present": present, "referenced": live, "unreferenced": dead}


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("elf", type=Path)
    ap.add_argument("--namespace", default="N7CamUser",
                    help="class-name prefix to report on (default N7CamUser)")
    ap.add_argument("--filter", default=None,
                    help="only report classes whose name contains this")
    a = ap.parse_args(argv)

    elf = Elf(a.elf.read_bytes())
    print("%s: %d bytes, %d PT_LOAD" % (a.elf.name, len(elf.d), len(elf.loads)))
    for off, va, fsz, fl in elf.loads:
        print("  off=0x%08x va=0x%08x filesz=0x%08x flags=%d delta=0x%x"
              % (off, va, fsz, fl, va - off))

    r = classify(elf, a.namespace)
    pres, ref, unref = r["present"], r["referenced"], r["unreferenced"]
    print("\n%s: %d classes compiled in, %d RTTI-referenced, %d string-only"
          % (a.namespace, len(pres), len(ref), len(unref)))
    if a.filter:
        ref = {k: v for k, v in ref.items() if a.filter in k}
        unref = {k: v for k, v in unref.items() if a.filter in k}
        pres = {k: v for k, v in pres.items() if a.filter in k}
        refc, unrefc = len(ref), len(unref)
    else:
        refc, unrefc = len(ref), len(unref)
    print("\n  RTTI REFERENCED (%d):" % refc)
    for k in sorted(ref):
        # ref maps name -> file offset of the name; count the referencing words
        # separately since classify() only records presence.
        print("    %s" % k)
    print("\n  STRING ONLY, no RTTI reference (%d):" % unrefc)
    for k in sorted(unref):
        print("    %s" % k)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
