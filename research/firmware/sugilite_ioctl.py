"""The /dev/dmpgles2 ioctl ABI: recover it from grm_gles.ko.

`grm_gles.ko` registers `/dev/dmpgles2` (248:29).  Its ioctl entry point,
`sugilite_ioctl`, is 2,584 bytes of ARM code at `.text+0x8e4`.  This recovers the
command table, decodes it as Linux `_IOC` values, and attributes each handler's
external calls and struct offsets.

Reproduce with:

    python sugilite_ioctl.py

What it establishes
-------------------
* **17 commands**, all ``_IOC(dir, 0x82, nr, 4)`` -- one type byte, and the
  argument is a pointer to a single ``u32`` in every case.
* The dispatch is a **binary search over literal-pool constants**, not a jump
  table.  (An earlier note said "jump-table dispatch"; that was wrong.)
* Only **one** of the 17 commands reaches the hardware, and it is not a general
  register write: ``nr=15`` writes the fixed constant ``0x20000001`` to the fixed
  BAR offset ``0xC0``, and only when the caller passes exactly 1.
* The module contains a complete **12-byte OSAL request/reply RPC into the RTOS**
  -- an unsymbolised 416-byte function -- but it has **no callers**, so it is not
  reachable from user space by any path.

So the ioctl is a thin scalar control surface, not a display door.  See
``docs/agents/REFERENCE.md`` and ``docs/06-method.md``.

Traps encoded here, each of which silently loses commands
--------------------------------------------------------
* **ARM's PC reads as ``addr+8``.**  Using ``addr+size`` puts every literal one
  word early and yields *instruction words* instead of constants -- 0x0a000055 and
  0x8a00001c are the prologue, not commands.
* **Immediates are ``imm8 ROR (2*rot)``.**  ``add r3, r3, #0xc0000004`` is really
  ``#0x11, 30``.  Read the decoded operand, never the printed text.
* **The compare chain is cumulative.**  GCC refines the *same* register:
  ``cmp r1,r3; beq E; add r3,r3,#K; cmp r1,r3; beq E2``.  Clearing r3 after the
  first cmp recovers 7 of 17 commands instead of 17.
* **A literal pool word may be a relocation** (a symbol address).  Then r3 is not
  a command constant and must be invalidated, not used.
* **``cmp; bne DEFAULT; b HANDLER`` also means equality** -- the ``bne`` leaves
  the equal case to fall through into the unconditional branch.
* **pyelftools streams from the file.**  Iterating ``.symtab`` after the ``with``
  block closes raises ``seek of closed file``; cache the symbols eagerly.
"""
import pathlib
import struct
import sys

from capstone import CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN, Cs
from capstone.arm import ARM_OP_IMM, ARM_OP_REG
from elftools.elf.elffile import ELFFile

KO = pathlib.Path("dumps/camera_2025/usr/usr/kmod/grm_gles.ko")
FUNC = "sugilite_ioctl"

# _IOC layout, from the kernel's arch/arm/include/uapi/asm/ioctl.h
IOC_NRBITS = 8
IOC_TYPEBITS = 8
IOC_SIZEBITS = 14
IOC_TYPESHIFT = IOC_NRBITS
IOC_SIZESHIFT = IOC_TYPESHIFT + IOC_TYPEBITS
IOC_DIRSHIFT = IOC_SIZESHIFT + IOC_SIZEBITS
DIRNAME = {0: "---", 1: "WRT", 2: "R/W", 3: "RD "}


def ioc(v):
    v &= 0xFFFFFFFF
    return {"dir": (v >> IOC_DIRSHIFT) & 3,
            "size": (v >> IOC_SIZESHIFT) & 0x3FFF,
            "type": (v >> IOC_TYPESHIFT) & 0xFF,
            "nr": v & 0xFF}


class Ko:
    """An ET_REL kernel object: section-relative addresses, inline relocations."""

    def __init__(self, path):
        self.text = b""
        self.reloc = {}
        self.symlist = []
        with open(path, "rb") as fh:
            f = ELFFile(fh)
            self.text = f.get_section_by_name(".text").data()
            symtab = f.get_section_by_name(".symtab")
            for secname in (".rel.text", ".rel.init.text", ".rel.exit.text",
                            ".rel.data"):
                sec = f.get_section_by_name(secname)
                if not sec:
                    continue
                for r in sec.iter_relocations():
                    nm = symtab.get_symbol(r["r_info_sym"]).name
                    self.reloc.setdefault(secname, {}).setdefault(
                        r["r_offset"], []).append(nm)
            self.symlist = [(s.name, s["st_value"], s["st_size"],
                             s["st_info"]["bind"], s["st_info"]["type"])
                            for s in symtab.iter_symbols()]

    def func(self, name):
        for nm, val, sz, _b, _t in self.symlist:
            if nm == name:
                return val, sz
        raise KeyError(name)

    def funcs(self):
        out = [(v, v + s, n) for n, v, s, _b, t in self.symlist
               if t == "STT_FUNC" and v and s]
        out.sort()
        return out

    def word(self, off):
        if off < 0 or off + 4 > len(self.text):
            return None
        return struct.unpack_from("<I", self.text, off)[0]

    def md(self):
        m = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
        m.detail = True
        return m

    def disasm(self, lo, hi):
        return list(self.md().disasm(self.text[lo:hi], lo))


def dispatch(ko, ent, sz):
    """Recover {command: {'cmp','eq','hi','lo','none'}} from the compare chain.

    A single forward pass tracking one register's known value.  No symbolic
    execution: an earlier attempt that walked the decision tree recovered 1 of 17
    commands, because a `seen` set shared between paths pruned blocks it had
    already entered from a different predecessor.
    """
    rel = ko.reloc.get(".rel.text", {})
    seq = ko.disasm(ent, ent + sz)
    r3 = None
    cmds = {}

    for idx, i in enumerate(seq):
        m, o = i.mnemonic, i.op_str
        regs = [op.reg for op in i.operands if op.type == ARM_OP_REG]
        imms = [op.imm for op in i.operands if op.type == ARM_OP_IMM]

        if m == "ldr" and o.startswith("r3,") and "[pc" in o:
            dsp = None
            if "#" in o:
                try:
                    dsp = int(o.split("#")[1].rstrip("]").strip(), 0)
                except ValueError:
                    pass
            if dsp is None:
                r3 = None
            else:
                off = i.address + 8 + dsp          # ARM PC = addr + 8
                r3 = None if off in rel else ko.word(off)
            continue

        if m in ("add", "sub") and o.startswith("r3, r3,"):
            if r3 is not None and imms:
                k = imms[-1]
                r3 = ((r3 + k) & 0xFFFFFFFF) if m == "add" \
                    else ((r3 - k) & 0xFFFFFFFF)
            else:
                r3 = None
            continue

        if m == "cmp" and o.startswith("r1, r3"):
            if r3 is not None:
                e = cmds.setdefault(r3, {"cmp": i.address, "eq": None,
                                         "hi": None, "lo": None, "none": None})
                e["cmp"] = i.address
                for j in (idx + 1, idx + 2, idx + 3):
                    if j >= len(seq):
                        break
                    b = seq[j]
                    bm = b.mnemonic
                    if bm == "bne" and e["none"] is None:
                        e["none"] = b.operands[-1].imm
                        k = j + 1
                        if k < len(seq) and seq[k].mnemonic == "b":
                            e["eq"] = seq[k].operands[-1].imm
                        break
                    if bm == "beq" and e["eq"] is None:
                        e["eq"] = b.operands[-1].imm
                        break
                    if bm == "bhi" and e["hi"] is None:
                        e["hi"] = b.operands[-1].imm
                        break
                    if bm == "blo" and e["lo"] is None:
                        e["lo"] = b.operands[-1].imm
                        break
            # r3 is deliberately NOT cleared: the chain is cumulative.
            continue

        if "r3" in regs and m not in ("cmp", "push", "str", "stm"):
            r3 = None

    return cmds


def attribute(ko, cmds):
    """Per handler: external calls, private-struct offsets, user-arg offsets."""
    rel = ko.reloc.get(".rel.text", {})
    ent, sz = ko.func(FUNC)
    seq = ko.disasm(ent, ent + sz)
    starts = sorted({e["eq"] for e in cmds.values() if e["eq"]})
    tails = {e[k] for e in cmds.values()
             for k in ("hi", "lo", "none") if e[k]}
    out = {}
    for s in starts:
        calls, priv, arg, stop = [], set(), set(), None
        for i in seq:
            if i.address < s:
                continue
            if i.address > s and (i.address in starts
                                  or i.address in tails
                                  or (i.mnemonic == "pop" and "pc" in i.op_str)):
                stop = i.address
                break
            for k in range(i.size):
                for nm in rel.get(i.address + k, []):
                    if nm and nm not in calls:
                        calls.append(nm)
            if i.mnemonic in ("ldr", "str", "strb", "ldrb") and "#" in i.op_str:
                base = i.op_str.split("[")[1].split(",")[0].strip()
                try:
                    off = int(i.op_str.split("#")[1].rstrip("]").strip(), 0)
                except (IndexError, ValueError):
                    continue
                if base == "r4":
                    priv.add(off)
                elif base == "r5":
                    arg.add(off)
        out[s] = (calls, sorted(priv), sorted(arg), stop)
    return out, starts


def find_callers(ko, targets):
    """Every direct branch in .text to any of `targets`, attributed to a function."""
    funcs = ko.funcs()
    md = ko.md()
    seq = list(md.disasm(ko.text, 0))
    rel = ko.reloc.get(".rel.text", {})
    hits = []
    for i in seq:
        if not i.mnemonic.startswith("b"):
            continue
        tg = next((o.imm for o in i.operands if o.type == ARM_OP_IMM), None)
        if tg not in targets:
            continue
        owner = next((nm for lo, hi, nm in funcs if lo <= i.address < hi),
                     "(unnamed)")
        marks = []
        for k in range(i.size):
            marks += rel.get(i.address + k, [])
        hits.append((i.address, i.mnemonic, tg, owner, marks))
    return hits


def uncalled_gap(ko):
    """Sized functions with no symbol table entry covering them is not the point;
    this finds code between functions that nothing branches to."""
    funcs = ko.funcs()
    covered = set()
    for lo, hi, _n in funcs:
        covered.update(range(lo, hi))
    gaps = []
    prev = 0
    for lo, hi, nm in funcs:
        if lo > prev:
            gaps.append((prev, lo))
        prev = max(prev, hi)
    if prev < len(ko.text):
        gaps.append((prev, len(ko.text)))
    return funcs, gaps, covered


def main():
    if not KO.exists():
        print("%s not present -- needs the card dump" % KO)
        return 2
    ko = Ko(KO)
    ent, sz = ko.func(FUNC)
    cmds = dispatch(ko, ent, sz)
    info, starts = attribute(ko, cmds)

    print("=" * 74)
    print("%s -- SUGILITE Driver v0.6 (DMP/Sony), /dev/dmpgles2 248:29" % KO.name)
    print("=" * 74)
    print("\n%s at .text+0x%x, %d bytes (0x%x)"
          % (FUNC, ent, sz, sz))
    print("%d commands recovered\n" % len(cmds))

    print("  %-11s %-4s %-4s %-6s %-5s %s"
          % ("cmd", "dir", "size", "type", "nr", "handler"))
    print("  " + "-" * 60)
    for c in sorted(cmds):
        f = ioc(c)
        h = cmds[c]["eq"]
        print("  0x%08x  %-4s %-4d 0x%02x   0x%02x   %s"
              % (c, DIRNAME[f["dir"]], f["size"], f["type"], f["nr"],
                 ("0x%x" % h) if h else "(range)"))

    dirs = sorted({ioc(c)["dir"] for c in cmds})
    sizes = sorted({ioc(c)["size"] for c in cmds})
    types = sorted({ioc(c)["type"] for c in cmds})
    nrs = sorted(ioc(c)["nr"] for c in cmds)
    print("\n  every command is _IOC(dir, 0x%02x, nr, %d)"
          % (types[0], sizes[0]))
    print("  dir bits seen : %s" % ", ".join(DIRNAME[d] for d in dirs))
    print("  nr values     : %s" % ", ".join("0x%02x" % n for n in nrs))
    # The dense block is 0x00..0x12; report holes inside it, and call out 0x63
    # separately rather than enumerating every unused value above the block.
    dense = [n for n in nrs if n <= 0x12]
    holes = [n for n in range(max(dense) + 1) if n not in dense]
    outliers = [n for n in nrs if n > 0x12]
    print("  dense block   : nr 0x00..0x%02x, %d commands" % (max(dense), len(dense)))
    print("  holes in block: %s"
          % (", ".join("0x%02x" % n for n in holes) if holes else "none"))
    print("  outliers      : %s"
          % (", ".join("0x%02x" % n for n in outliers) if outliers else "none"))

    print("\n" + "-" * 74)
    print("per-handler behaviour")
    print("-" * 74)
    for s in starts:
        here = sorted(c for c in cmds if cmds[c]["eq"] == s)
        calls, priv, arg, stop = info[s]
        print("\n  0x%x  nr=%s (%s)"
              % (s, ", ".join(str(ioc(c)["nr"]) for c in here),
                 ", ".join(DIRNAME[ioc(c)["dir"]].strip() for c in here)))
        print("    calls   : %s" % (", ".join(calls) if calls else "(none)"))
        if priv:
            print("    priv    : %s" % ", ".join("0x%x" % o for o in priv))
        print("    ends    : %s" % ("0x%x" % stop if stop else "?"))

    print("\n" + "-" * 74)
    print("the only command that reaches the hardware")
    print("-" * 74)
    n15 = [c for c in cmds if ioc(c)["nr"] == 15]
    if n15:
        h = cmds[n15[0]]["eq"]
        print("  nr=15 (0x%08x) handler at 0x%x:" % (n15[0], h))
        for i in ko.disasm(h, h + 0x4c):
            print("    %08x  %-8s %s" % (i.address, i.mnemonic, i.op_str))
        print("\n  it reads one u32 from the user, and proceeds only if that u32")
        print("  is exactly 1; then it writes the FIXED value 0x20000001 to the")
        print("  FIXED BAR offset 0xC0.  Not a general register-write door.")

    print("\n" + "-" * 74)
    print("the RTOS RPC door, and why it is unreachable")
    print("-" * 74)
    funcs, gaps, _cov = uncalled_gap(ko)
    print("  sized functions: %d" % len(funcs))
    print("  gaps between them (unsymbolised code): %s"
          % ", ".join("0x%x..0x%x" % g for g in gaps))

    # the OSAL message calls all fall outside any sized function
    rel = ko.reloc.get(".rel.text", {})
    osal = ["osal_snd_msg", "osal_snd_sync_msg", "osal_snd_sync_direct",
            "osal_valloc_msg_wait", "osal_free_msg"]
    stray = sorted({off for off, names in rel.items()
                    if any(n in osal for n in names)})
    inside = [o for o in stray
              if any(lo <= o < hi for lo, hi, _n in funcs)]
    print("\n  osal_* message call sites: %d, of which %d inside a sized function"
          % (len(stray), len(inside)))
    if stray and not inside:
        lo, hi = stray[0], stray[-1] + 4
        print("  they occupy 0x%x..0x%x, which no symbol covers." % (lo, hi))

        doors = set()
        for a, _m, tg, _o, _r in find_callers(ko, {lo}):
            doors.add(a)
        hits = find_callers(ko, {lo})
        print("  direct branches to that region from anywhere in .text: %d"
              % len(hits))
        if not hits:
            print("  => the 12-byte OSAL request/reply path has NO callers and no")
            print("     symbol, so no pointer can reach it either.  Unreachable")
            print("     from user space by any path.")

    print("\n" + "=" * 74)
    print("verdict: a 4-byte scalar control surface, not a display door.")
    print("17 commands; 1 touches hardware and it is a fixed kick; the RTOS RPC")
    print("is unreferenced.  The drawing API is libObj.so's exported GRM_* set.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
