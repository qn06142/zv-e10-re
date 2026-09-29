"""The MWF object/message id pair, read off the call sites.

The DataflowInfra plugins (AVBB/CAMERA) pass one id to SendASync.  The MWF
plugins (MPR_*) do not: they build an `MWF::ObjMsg`, whose constructor is

    MWF::ObjMsg::ObjMsg(unsigned int, unsigned int)

-- two ids, and the reader is `MWF::ObjMsg::GetCategoryId()` plus
`MWF::ObjMsg::GetMessageId()`.  So the MWF command space is two-dimensional
and the category is the outer one.

A representative call site, from MPR_SCN_FORMAT.so:

    18c0  add  r0, sp, #0x238      ; the ObjMsg to construct
    18c4  mov  r1, #0x3800         ; category
    18c8  mov  r2, #1              ; message id
    18cc  str  r3, [sp, #0x248]
    18d0  bl   0x1300             ; -> MWF::ObjMsg::ObjMsg(uint, uint)

This sweeps every such call and reports the (category, message) pairs, so the
outer namespace can be compared with the flat one the DataflowInfra plugins
use.

Traps, all of which fail silently rather than raising:
  * Thumb: decode at st_value & ~1.
  * The PLT is ARM even so, and plt_map() must resolve it or no call site can
    be identified at all -- see docs/RE_METHOD.md.
  * r0 is the *object* being constructed, not an id. Only r1 and r2 are ids.
"""
import collections
import pathlib
import sys

from capstone import CS_ARCH_ARM, CS_MODE_THUMB, Cs
from elftools.elf.elffile import ELFFile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from annotate import load, load_segs, plt_map, v2o  # noqa: E402
from scenario_vocab import SCEN, demangle  # noqa: E402

OBJM_MSG_CTOR = "_ZN3MWF6ObjMsgC1Ejj"          # ObjMsg::ObjMsg(uint, uint)
OBJM_SETCAT = "_ZN3MWF6ObjMsg14SetCateIdMsgIdEjj"  # ObjMsg::SetCateIdMsgId


def const_reg(insns, idx, segs=None, data=None, width=24):
    """Value in r1/r2 at instruction idx.

    Follows the forms these call sites actually use:
      movw/movt pairs, mov.w/movs/mov with an immediate, register-to-register
      moves, and `ldr rX, [pc, #imm]` from a literal pool.  All three appear
      within a couple of instructions of the call, and missing any one of them
      silently turns a real id into "(reg)".
    """
    reg = {}
    for j in range(max(0, idx - width), idx + 1):
        ins = insns[j]
        m = ins.mnemonic
        op = ins.op_str
        if m in ("movw", "movt") and "#" in op:
            r, v = op.split("#")
            # op_str for a movw is "r2, #0x1022", so the register keeps a
            # trailing comma.  Left in, the key becomes "r2," and every later
            # lookup for "r2" misses -- which shows up as the id silently
            # falling back to the category value.
            r = r.strip().rstrip(",").strip()
            try:
                v = int(v, 0) & 0xFFFF
            except ValueError:
                continue
            if m == "movw":
                reg[r] = v
            elif r in reg:
                reg[r] |= v << 16
        elif m in ("mov.w", "movs", "mov") and ", " in op:
            a, b = op.split(", ")
            a, b = a.strip(), b.strip()
            if b.startswith("#"):
                try:
                    reg[a] = int(b[1:], 0) & 0xFFFFFFFF
                except ValueError:
                    pass
            elif a in reg:
                reg[b] = reg[a]
        elif m == "ldr" and "[pc" in op and ", " in op:
            dst = op.split(",")[0].strip()
            if segs is not None and data is not None:
                try:
                    imm = int(op.split("#")[-1].rstrip("]"), 0)
                    tgt = (ins.address + 4 + imm) & ~3
                    to = v2o(segs, tgt)
                    if to is not None:
                        reg[dst] = int.from_bytes(data[to:to + 4], "little")
                except Exception:
                    pass
        elif m in ("bl", "blx"):
            reg.pop("r0", None)
    r1, r2 = reg.get("r1"), reg.get("r2")
    # `movs r1, #1 ; mov r2, r1` -- the id is copied out of the category
    # register rather than loaded again.  Only fall back when r2 was genuinely
    # never written in the window: a `movw r2, #imm` immediately before the
    # call is a real value and must not be overwritten by the category.
    if r2 is None and r1 is not None:
        r2 = r1
    return r1, r2


def scan(path):
    p = pathlib.Path(path)
    data = p.read_bytes()
    f = ELFFile(open(p, "rb"))
    segs = load_segs(f)
    plt = plt_map(f, data, segs)
    slots = {k for k, v in plt.items() if v in (OBJM_MSG_CTOR, OBJM_SETCAT)}
    if not slots:
        return []
    ds = f.get_section_by_name(".dynsym")
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    out = []
    for s in ds.iter_symbols() if ds else []:
        if not (s.name and s["st_size"] and s["st_info"]["type"] == "STT_FUNC"):
            continue
        v = s["st_value"] & ~1
        off = v2o(segs, v)
        if off is None:
            continue
        insns = list(md.disasm(data[off:off + s["st_size"]], v))
        for idx, ins in enumerate(insns):
            if ins.mnemonic in ("bl", "blx") and ins.op_str.startswith("#"):
                t = int(ins.op_str[1:], 0) & ~1
                if t in slots:
                    r1, r2 = const_reg(insns, idx, segs, data)
                    if r1 is not None:
                        out.append((demangle(s.name), plt[t], r1, r2,
                                    "0x%04x" % ins.address))
    return out


def main():
    plugins = sorted(SCEN.glob("*.so"))
    # scan() yields (function, ctor, category, message, site); the plugin name
    # goes on the front, so a row is 6 wide and category is index 3.
    rows = []
    for p in plugins:
        rows += [(p.name,) + r for r in scan(p)]
    if not rows:
        print("no MWF::ObjMsg construction sites found")
        return 1

    print("MWF::ObjMsg construction sites: %d\n" % len(rows))
    cats = collections.Counter(r[3] for r in rows)
    print("=== category id (r1) ===")
    for c, n in sorted(cats.items()):
        print("  0x%08x  %d" % (c, n))
    print()
    print("=== (category, message) pairs ===")
    for name, fn, ctor, c, m, site in sorted(rows, key=lambda r: (r[3], r[4] or 0)):
        print("  %-30s cat=0x%08x msg=%-8s %s" % (name.replace(".so", "")[:30],
                                                  c,
                                                  ("0x%x" % m) if m is not None
                                                  else "(reg)", site))
    return 0


if __name__ == "__main__":
    sys.exit(main())
