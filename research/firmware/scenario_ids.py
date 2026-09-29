"""What the 35 scenario plugins send, and to whom.

Why the plugins are worth this
-----------------------------
The service filesystem cannot load the application, so /usr/scenario/*.so is
the one place in the tree where the camera's own interface to its subsystems
is still readable.  Each plugin is a small ARM ELF exporting `scenario_run`,
and each one is a worked example of a real call into a real subsystem.

Two RPC frameworks appear, which is itself the finding:

  DataflowInfra*   18 plugins   raw osal messages, destination id passed to
                                SendASync(unsigned int, DataflowInfraMsg*)
  MWF::*            8 plugins   the object/message framework: ObjIf, ObjMsg,
                                EventSender/Receiver, pins, signals

The open question this answers is the destination ids.  Nothing in the earlier
work mapped a plugin to a subsystem, because the ids are not stored as data --
they are immediates inside the code, passed to SendASync at the call site.
So they have to be read out of the disassembly.

Method, and why each step is needed (see docs/RE_METHOD.md):
  1. Thumb: .dynsym sets bit 0 on st_value.  Decode at st_value & ~1 or the
     output is fictional.
  2. Resolve the PLT so `SendASync` is recognisable at the call site.  The PLT
     is ARM even in a Thumb object, and there are three stub encodings.
  3. At a call to SendASync, the first argument (r0) is the destination id.
     It is set by a movw/movt pair or a literal-pool load immediately before
     the call, so walk back and reconstruct it.
"""
import collections
import pathlib
import re
import struct
import sys

import cpp_demangle
from capstone import CS_ARCH_ARM, CS_MODE_THUMB, Cs
from elftools.elf.elffile import ELFFile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from annotate import load_segs, plt_map, v2o  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCEN = ROOT / "dumps" / "camera_2025" / "usr" / "usr" / "scenario"


def demangle(name):
    if not name.startswith("_Z"):
        return name
    try:
        return cpp_demangle.demangle(name)
    except Exception:
        return name


def analyse(path):
    """Return (imports, calls) for one plugin.

    calls: list of (func, dest_id, site) for every SendASync/IssueCommand
    call where the destination id could be reconstructed.
    """
    p = pathlib.Path(path)
    data = p.read_bytes()
    f = ELFFile(open(p, "rb"))
    segs = load_segs(f)
    plt = plt_map(f, data, segs)
    ds = f.get_section_by_name(".dynsym")
    if not ds:
        return {}, []

    imports = {}
    funcs = []
    for s in ds.iter_symbols():
        if not s.name:
            continue
        d = demangle(s.name)
        if s["st_shndx"] == "SHN_UNDEF":
            imports[d] = imports.get(d, 0) + 1
        elif s["st_size"] and s["st_info"]["type"] == "STT_FUNC":
            funcs.append((s["st_value"] & ~1, s["st_size"], d))

    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    calls = []
    for vaddr, size, fname in funcs:
        off = v2o(segs, vaddr)
        if off is None:
            continue
        insns = list(md.disasm(data[off:off + size], vaddr))
        # track movw/movt into a register, and ldr from a literal pool
        reg = {}
        for idx, ins in enumerate(insns):
            m = ins.mnemonic
            if m == "movw" and "#" in ins.op_str:
                r, v = ins.op_str.split("#")
                reg[r.strip()] = int(v, 0) & 0xFFFF
            elif m == "movt" and "#" in ins.op_str:
                r, v = ins.op_str.split("#")
                r = r.strip()
                if r in reg:
                    reg[r] |= (int(v, 0) & 0xFFFF) << 16
            elif m == "mov":
                parts = ins.op_str.split(", ")
                if len(parts) == 2 and parts[0].strip() in reg:
                    reg[parts[1].strip()] = reg[parts[0].strip()]
            elif m == "ldr" and "[pc" in ins.op_str:
                try:
                    imm = int(ins.op_str.split("#")[-1].rstrip("]"), 0)
                    tgt = (ins.address + 4 + imm) & ~3
                    to = v2o(segs, tgt)
                    if to is not None:
                        parts = ins.op_str.split(",")
                        reg[parts[0].strip()] = struct.unpack_from(
                            "<I", data, to)[0]
                except Exception:
                    pass

            if m in ("bl", "blx") and ins.op_str.startswith("#"):
                tgt = int(ins.op_str[1:], 0) & ~1
                name = plt.get(tgt)
                if name and ("SendASync" in name or "IssueCommand" in name
                             or "SendAndRecv" in name or "SetSendId" in name):
                    calls.append((demangle(name), reg.get("r0"),
                                  "0x%04x" % ins.address))
            # a call clobbers r0-r3, so the tracked value stops being valid
            if m in ("bl", "blx"):
                for r in ("r0", "r1", "r2", "r3"):
                    reg.pop(r, None)
    return imports, calls


def main():
    targets = sorted(SCEN.glob("*.so"))
    if not targets:
        print("no plugins found at %s" % SCEN)
        return 1

    allids = collections.Counter()
    per_plugin = {}
    for p in targets:
        imports, calls = analyse(p)
        ids = [c[1] for c in calls if c[1] is not None]
        for i in ids:
            allids[i] += 1
        per_plugin[p.name] = (imports, calls, ids)

    print("plugins: %d" % len(targets))
    print()
    print("=== destination ids passed to the RPC entry points ===")
    for pid, n in sorted(allids.items(), key=lambda kv: -kv[1]):
        print("  0x%08x  %-9d %s" % (pid, n,
              "0x00dc family (liro/RTOS)" if 0x00dc0000 <= pid <= 0x00dcffff
              else "0x0094 family (Linux)" if 0x00940000 <= pid <= 0x0094ffff
              else ""))
    print()
    print("  distinct destination ids: %d" % len(allids))
    return 0


if __name__ == "__main__":
    sys.exit(main())
