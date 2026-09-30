"""The scenario plugins' command-id vocabulary, read out of the code.

What this is for
----------------
/usr/scenario/*.so is the one place in the tree where the camera's own
interface to its subsystems is still readable: 35 small ARM ELFs, each
exporting `scenario_run`, each a worked example of a real call into a real
subsystem.  Earlier work established that scenario.elf does *not* dlopen them
-- libtestcmd.so sends the name over the UIPC bus and the peer loads it -- so
these files are the only surviving description of what the scenarios actually
do.

The finding
-----------
The destination ids are not stored as data anywhere.  They are immediates in
the code, built by `movw`/`movt` pairs and passed to the RPC entry points.
Sweeping those immediates across all 35 plugins gives a structured 16-bit
vocabulary with a clear shape:

    0x2004  76 uses      0x0301  16      0x8102  10
    0x2001  17          0x0313  12      0x1001  10
    0x0401  12          0x1002   8      0x0303   8

The high nibble groups by subsystem and the low byte appears to be a
sub-command -- 0x03xx and 0x04xx sit together, 0x10xx together, 0x80xx/0x83xx
together -- and 0x2004 and 0x2001 dominate, which is the common path.

Note these are NOT the 0x00dc0000 osal_id family.  That is the endpoint the
*bus* addresses; these are the per-subsystem command ids carried inside the
message.  Two different layers, and conflating them is what made the earlier
"sndcmd needs an osal_id" question look unanswerable.

Method and its traps: see 06-method.md.  In short, the objects are Thumb
(.dynsym sets bit 0), the PLT is ARM even so, and resolving a stub requires
decoding its `ldr pc, [ip, #imm]!` to find the GOT word.
"""
import collections
import pathlib
import sys

import cpp_demangle
from capstone import CS_ARCH_ARM, CS_MODE_THUMB, Cs
from elftools.elf.elffile import ELFFile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from annotate import load, load_segs, v2o  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCEN = ROOT / "dumps" / "camera_2025" / "usr" / "usr" / "scenario"


def demangle(name):
    """Itanium C++ name -> readable form, or the original if it will not budge.

    cxxfilt is useless here: it shells out to a C++ demangler that is not
    installed, and fails with 'Cannot find any of libraries'. cpp_demangle is
    pure python and works.  Local symbols like _Z19SndDataFlowMsgAsyncP... are
    not always well-formed, hence the fallback.
    """
    if not name.startswith("_Z"):
        return name
    try:
        return cpp_demangle.demangle(name)
    except Exception:
        return name


def immediates(path):
    """(movw/movt immediate -> count, and the 32-bit values they build)."""
    p = pathlib.Path(path)
    data = p.read_bytes()
    f = ELFFile(open(p, "rb"))
    segs = load_segs(f)
    ds = f.get_section_by_name(".dynsym")
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

    words = collections.Counter()
    pairs = collections.Counter()
    for s in ds.iter_symbols() if ds else []:
        if not (s.name and s["st_size"] and s["st_info"]["type"] == "STT_FUNC"):
            continue
        vaddr = s["st_value"] & ~1
        off = v2o(segs, vaddr)
        if off is None:
            continue
        pending = {}
        for ins in md.disasm(data[off:off + s["st_size"]], vaddr):
            if ins.mnemonic in ("movw", "movt") and "#" in ins.op_str:
                reg, val = ins.op_str.split("#")
                reg = reg.strip()
                try:
                    val = int(val, 0) & 0xFFFF
                except ValueError:
                    continue
                words[(ins.mnemonic, val)] += 1
                if ins.mnemonic == "movw":
                    pending[reg] = val
                elif reg in pending:
                    full = (val << 16) | pending[reg]
                    pairs[full] += 1
                    pending.pop(reg, None)
            elif ins.mnemonic not in ("movw", "movt"):
                # any other instruction may clobber; be conservative
                pending.clear()
    return words, pairs


def main():
    plugins = sorted(SCEN.glob("*.so"))
    if not plugins:
        print("no plugins at %s" % SCEN)
        return 1

    all_words = collections.Counter()
    all_pairs = collections.Counter()
    per = {}
    for p in plugins:
        w, pr = immediates(p)
        all_words += w
        all_pairs += pr
        per[p.name] = (w, pr)

    print("plugins analysed: %d" % len(plugins))
    print()
    print("=== 32-bit values built by a movw/movt pair ===")
    if not all_pairs:
        print("  none -- the ids are single movw, see below")
    for val, n in sorted(all_pairs.items(), key=lambda kv: -kv[1]):
        print("  0x%08x  %3d  %s" % (val, n, family(val)))
    print()
    print("=== movw immediates, grouped by high nibble ===")
    byhigh = collections.defaultdict(list)
    for (m, val), n in all_words.items():
        if m == "movw":
            byhigh[val >> 12].append((val, n))
    for hi in sorted(byhigh):
        items = sorted(byhigh[hi])
        tot = sum(n for _, n in items)
        vals = " ".join("0x%03x(%d)" % (v, n) for v, n in items)
        print("  0x%x___  %3d uses  %s" % (hi, tot, vals))
    print()
    print("  distinct movw immediates: %d" % len(
        {v for (m, v) in all_words if m == "movw"}))
    return 0


def family(val):
    if 0x00DC0000 <= val <= 0x00DCFFFF:
        return "0x00dc family (liro/RTOS endpoint)"
    if 0x00940000 <= val <= 0x0094FFFF:
        return "0x0094 family (Linux endpoint)"
    return "per-subsystem command id"


if __name__ == "__main__":
    sys.exit(main())
