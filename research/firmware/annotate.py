"""Annotate a Thumb-2 disassembly of a named function with:
  - PLT stub -> imported symbol name (from .rel.plt)
  - literal pool loads -> decoded u32 (and ASCII if it looks like a string)
  - branch targets -> symbol names

Used to read Sony's OSAL UIPC message layout out of the code rather than
guessing it.  No disassembly of code we have not read.
"""
import pathlib
import struct
import sys

from capstone import CS_ARCH_ARM, CS_MODE_THUMB, Cs
from elftools.elf.elffile import ELFFile


def load(path):
    p = pathlib.Path(path)
    data = p.read_bytes()
    f = ELFFile(open(p, "rb"))
    return data, f


def load_segs(f):
    return [s for s in f.iter_segments() if s["p_type"] == "PT_LOAD" and s["p_filesz"]]


def v2o(segs, v):
    for seg in segs:
        if seg["p_vaddr"] <= v < seg["p_vaddr"] + seg["p_filesz"]:
            return seg["p_offset"] + (v - seg["p_vaddr"])
    return None


def o2v(segs, o):
    for seg in segs:
        if seg["p_offset"] <= o < seg["p_offset"] + seg["p_filesz"]:
            return seg["p_vaddr"] + (o - seg["p_offset"])
    return None


def symtab(f):
    out = {}
    for sn in (".dynsym", ".symtab"):
        sec = f.get_section_by_name(sn)
        if not sec:
            continue
        for s in sec.iter_symbols():
            if s.name and s["st_size"] and s["st_value"]:
                out.setdefault(s["st_value"] & ~1, (s.name, s["st_size"]))
    return out


def plt_map(f, data, segs):
    """PLT stub vaddr -> imported symbol name.

    Resolved by decoding each stub's ``ldr pc, [ip, #imm]!`` to find the GOT
    word it loads, then matching that GOT address against .rel.plt/.rel.dyn.
    Assuming stub order == relocation order gives wrong answers on these
    binaries, so we decode instead of guessing.
    """
    got = {}          # got address -> symbol name
    for rname in (".rel.plt", ".rel.dyn"):
        rela = f.get_section_by_name(rname)
        if not rela:
            continue
        dynsym = f.get_section(rela["sh_link"])
        for r in rela.iter_relocations():
            if r["r_info_type"] == 0:      # R_ARM_NONE placeholder
                continue
            got.setdefault(r["r_offset"], dynsym.get_symbol(r["r_info_sym"]).name)

    def ror8(w):
        """Decode an ARM modified-immediate (8-bit value, rotate field)."""
        imm = w & 0xFF
        rot = ((w >> 8) & 0xF) * 2
        if rot == 0:
            return imm
        return ((imm >> rot) | (imm << (32 - rot))) & 0xFFFFFFFF

    out = {}
    for sname in (".plt", ".plt.got", ".plt.sec", ".text"):
        sec = f.get_section_by_name(sname)
        if not sec:
            continue
        po, pv, n = sec["sh_offset"], sec["sh_addr"], sec["sh_size"]
        # .text is scanned too because the linker can emit the thunks inline
        # instead of into .plt; only matches that land on a real GOT slot count.
        i = 0
        while po + i + 8 <= po + n:
            w = struct.unpack_from("<3I", data, po + i)
            base = pv + i + 8                      # ARM: pc reads addr + 8
            # The ldr must be `ldr pc, [ip, #imm]!` -- a pre-indexed, writeback,
            # word load from ip into pc.  Test the ARM single-data-transfer bit
            # positions directly: P=24, U=23, B=22 (must be 0, word), W=21,
            # L=20, then Rn=ip and Rt=pc.
            #
            # No condition check.  Three earlier versions of this predicate were
            # wrong in ways that produced an empty result rather than an error:
            # one pinned the register field (rejecting the common e5bcf...
            # encoding), one used bit 21 for W when it is bit 21 *of the field*
            # but the mask was written as if for bit 20, and one masked the
            # condition with 0x0F000000, which is bits 24-27, not 28-31 -- so
            # it compared against P/U rather than cond.  All three fail silently.
            # Requiring only the bits that must be 1, and the two registers,
            # is enough: the GOT-slot lookup filters false positives.
            LDR_PC_IP_MASK = (1 << 24) | (1 << 23) | (1 << 21) | (1 << 20)

            def is_ldr_pc_ip(wd):
                return ((wd & LDR_PC_IP_MASK) == LDR_PC_IP_MASK
                        and not (wd & (1 << 22))          # B=0, word not byte
                        and ((wd >> 16) & 0xF) == 0xC      # Rn = ip
                        and ((wd >> 12) & 0xF) == 0xF)     # Rt = pc
            # 8-byte form:  add ip, sp/pc, #A ; ldr pc, [ip, #B]!
            if (w[0] & 0xFFFFF000) in (0xE28CC000, 0xE28FC000) and is_ldr_pc_ip(w[1]):
                gip = (base + ror8(w[0]) + (w[1] & 0xFFF)) & 0xFFFFFFFF
                if gip in got:
                    out[pv + i] = got[gip]
            # 12-byte form: add ip,pc,#A ; add ip,ip,#B,20 ; ldr pc,[ip,#C]!
            elif po + i + 12 <= po + n and \
                 (w[0] & 0xFFFFF000) == 0xE28FC000 and \
                 (w[1] & 0xFFFFF000) == 0xE28CC000 and is_ldr_pc_ip(w[2]):
                gip = (base + ror8(w[0]) + ror8(w[1]) + (w[2] & 0xFFF)) & 0xFFFFFFFF
                if gip in got:
                    out[pv + i] = got[gip]
            i += 4
    return out


def lit_pool(data, segs, lo, hi):
    """Decode a literal pool region as u32 words, annotate as strings."""
    o = v2o(segs, lo)
    end = v2o(segs, hi)
    if o is None or end is None:
        return []
    rows = []
    for off in range(o, end, 4):
        w = struct.unpack_from("<I", data, off)[0]
        note = ""
        # try to read as a NUL-terminated ASCII string if it points into a
        # plausible data address
        so = v2o(segs, w)
        if so is not None:
            s = data[so:so + 48].split(b"\0")[0]
            if len(s) >= 3 and all(32 <= c < 127 for c in s):
                note = repr(s.decode("latin1"))
        rows.append((o2v(segs, off), w, note))
    return rows


def annotate(path, want, mode=CS_MODE_THUMB, lo_addr=None, hi_addr=None):
    data, f = load(path)
    segs = load_segs(f)
    syms = symtab(f)
    plt = plt_map(f, data, segs)
    byname = {v[0]: (k, v[1]) for k, v in syms.items()}

    v, sz = byname[want]
    v &= ~1
    off = v2o(segs, v)
    md = Cs(CS_ARCH_ARM, mode)

    end = v + sz
    if lo_addr is not None:
        v, end, off = lo_addr, hi_addr, v2o(segs, lo_addr)

    print("=" * 100)
    print("%s  vaddr=0x%x  size=%d" % (want, v, end - v))
    print("=" * 100)
    for i in md.disasm(data[off:off + (end - v)], v):
        ann = ""
        if i.mnemonic in ("bl", "blx", "b", "beq", "bne", "blt", "bgt", "bge",
                          "ble", "bcc", "bcs", "bhi", "bls", "cbz", "cbnz",
                          "b.w", "beq.w", "bne.w", "blt.w", "bgt.w"):
            tgt = None
            op = i.op_str.strip()
            if op.startswith("#"):
                try:
                    tgt = int(op[1:], 0)
                except ValueError:
                    tgt = None
            if tgt is not None:
                tgt &= ~1
                if tgt in plt:
                    ann = "  ; -> %s" % plt[tgt]
                elif tgt in syms:
                    ann = "  ; -> %s" % syms[tgt][0]
        if i.mnemonic in ("ldr",) and "pc" in i.op_str:
            # literal load: compute target
            try:
                idx = int(i.op_str.split("#")[-1].rstrip("]"), 0)
                tgt = (i.address + 4 + idx) & ~3
                o = v2o(segs, tgt)
                if o is not None:
                    w = struct.unpack_from("<I", data, o)[0]
                    ann = "  ; =0x%08x" % w
                    so = v2o(segs, w)
                    if so is not None:
                        s = data[so:so + 64].split(b"\0")[0]
                        if len(s) >= 3 and all(32 <= c < 127 for c in s):
                            ann += " %r" % s.decode("latin1")
            except Exception:
                pass
        print("  %08x  %-12s %-34s%s" % (i.address, i.bytes.hex(),
                                          i.mnemonic + " " + i.op_str, ann))

    print()
    print("--- literal pool tail of function ---")
    for a, w, note in lit_pool(data, segs, v, end)[-14:]:
        print("  0x%08x  0x%08x  %s" % (a, w, note))


if __name__ == "__main__":
    annotate(sys.argv[1], sys.argv[2])
