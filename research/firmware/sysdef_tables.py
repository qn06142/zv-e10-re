"""The MWF id tables in libSysDef.so, resolved to names.

Why this file
-------------
`libSysDef.so` is 3.2 MB and exports almost nothing -- 18 symbols -- but three
of them are the tables the whole MWF command space is built from:

    MWF::MwfTbl::m_cateTbl    category table
    MWF::MwfTbl::m_pinTbl     pin table
    MWF::MwfTbl::m_objTbl     object table

That is the answer to a question the scenario plugins could not answer on their
own.  SCENARIO_VOCAB.md recovered ids like 0x3700, 0x6000 and 0x81003 out of
the plugins' code, but had no way to say *which subsystem* they name -- the
plugins carry no such table.  It is here, in a library, with the names in it.

Each table is an array of {u32 id, u32 name_offset} pairs, where the offset is
a vaddr into the same object.  So the table is self-describing: read 8 bytes,
follow the second word, and the name is right there.

The `DefInh::sm_refTbl` (3.1 MB) and `DefRsrc::scm_refTbl` (98 KB) are the
larger resource tables and the natural next target.
"""
import pathlib
import struct
import sys

from elftools.elf.elffile import ELFFile

ROOT = pathlib.Path(__file__).resolve().parents[2]
SYSDEF = ROOT / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libSysDef.so"

TABLES = [
    # (mangled suffix, label, record stride in bytes, which name to show)
    #
    # The strides differ, and guessing them fails in a way that produces
    # plausible-looking nonsense rather than an error:
    #
    #   m_cateTbl  8   {u32 id, u32 name}
    #   m_objTbl  12   {u32 id, u32 cate_name, u32 obj_name}
    #   m_pinTbl  16   {u32 id, u32 aux, u32 name, u32 name}
    #
    # The name pointer is the first u32 in the range that points into the
    # string area, and reading at the wrong stride lands on the wrong word: at
    # 8 the pin table yields "\x7fELF" (the ELF header at vaddr 0) and at 12
    # it interleaves the id column with the name column, so "PIN_PANEL"
    # appears against the id 0x1987a.
    #
    # m_objTbl carries TWO names per record, and picking by position gets it
    # backwards: the second word is the CATEID_ name and the third is the Obj*
    # name, so a positional read reports "ObjCntMgr" for 0x3700 when the
    # category is really CATEID_CNT_MGR.
    ("m_cateTbl", "MWF::MwfTbl::m_cateTbl  (categories)", 8, "CATEID_"),
    ("m_objTbl", "MWF::MwfTbl::m_objTbl   (objects)", 12, "Obj"),
    ("m_pinTbl", "MWF::MwfTbl::m_pinTbl   (pins)", 16, "PIN_"),
]


class Obj:
    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.data = self.path.read_bytes()
        self.f = ELFFile(open(self.path, "rb"))
        self.segs = [s for s in self.f.iter_segments()
                     if s["p_type"] == "PT_LOAD" and s["p_filesz"]]
        self.sym = {}
        ds = self.f.get_section_by_name(".dynsym")
        for s in ds.iter_symbols() if ds else []:
            if s.name and s["st_size"] and s["st_shndx"] != "SHN_UNDEF":
                self.sym[s.name] = (s["st_value"] & ~1, s["st_size"])

    def v2o(self, v):
        for s in self.segs:
            if s["p_vaddr"] <= v < s["p_vaddr"] + s["p_filesz"]:
                return s["p_offset"] + (v - s["p_vaddr"])
        return None

    def cstr(self, vaddr, limit=200):
        o = self.v2o(vaddr)
        if o is None:
            return None
        end = self.data.find(b"\x00", o, o + limit)
        if end < 0:
            return None
        try:
            return self.data[o:end].decode("ascii")
        except UnicodeDecodeError:
            return None

    def find(self, suffix):
        """Locate a data symbol by its mangled name.

        The names are itanium-mangled, so the member name is followed by the
        terminating 'E': _ZN3MWF6MwfTbl9m_cateTblE.  A plain endswith() on
        'm_cateTbl' therefore matches nothing, and the table appears to be
        absent.  Match the member name as a whole component instead.
        """
        for name, (v, sz) in self.sym.items():
            if name.endswith(suffix + "E") or name.endswith(suffix):
                return name, v, sz
        return None, None, None

    def pairs(self, vaddr, size, stride=8):
        """Yield (id, name, aux) for an array of fixed-stride records.

        The name pointer is identified by what it resolves to, not by position,
        because the tables carry two different string kinds and the earlier
        positional guess picked the wrong one: m_objTbl's records are
        {id, CATEID_*, Obj*} and reading the second word as the name yields
        "ObjCntMgr" for 0x3700 when the category name is CATEID_CNT_MGR.

        So: a pointer resolving to a CATEID_ string is the category name, one
        resolving to an Obj* string is the object name, and PIN_* is a pin.
        The other pointer is returned as aux.  Callers that only want the
        subsystem name should prefer whichever matches their table.
        """
        o = self.v2o(vaddr)
        if o is None:
            return
        for i in range(0, size - stride + 1, stride):
            words = list(struct.unpack_from("<%dI" % (stride // 4),
                                            self.data, o + i))
            cid = words[0]
            strs = []
            for w in words[1:]:
                s = self.cstr(w)
                strs.append(s if (s and all(32 <= ord(c) < 127 for c in s))
                            else None)
            yield cid, strs, words


def pick(strs, prefix):
    """The string in this record matching a name prefix, else the first."""
    for s in strs:
        if s and s.startswith(prefix):
            return s
    for s in strs:
        if s:
            return s
    return None


def main():
    if not SYSDEF.exists():
        print("missing %s" % SYSDEF)
        return 1
    o = Obj(SYSDEF)
    print("libSysDef.so  %d bytes, %d exports\n" % (len(o.data), len(o.sym)))

    out = []
    for suffix, label, stride, want in TABLES:
        name, vaddr, size = o.find(suffix)
        if not name:
            print("%-40s NOT FOUND" % label)
            continue
        rows = [(cid, pick(strs, want), [s for s in strs if s])
                for cid, strs, _w in o.pairs(vaddr, size, stride)]
        rows = [r for r in rows if r[1]]
        n = size // stride
        print("=== %s ===" % label)
        print("    %s  %d records of %d bytes, %d named\n"
              % (name, n, stride, len(rows)))
        for cid, nm, both in rows:
            other = [s for s in both if s != nm]
            extra = ("   also: " + ", ".join(other)) if other else ""
            print("  0x%08x  %-28s%s" % (cid, nm, extra))
        print()
        out.append((label, rows, stride))

    # cross-check against the ids recovered from the plugins
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        import mwf_ids
        mwf_cats = set()
        for p in sorted(mwf_ids.SCEN.glob("*.so")):
            for _fn, _ctor, cat, _msg, _site in mwf_ids.scan(p):
                if cat is not None:
                    mwf_cats.add(cat)
        if mwf_cats and out:
            known = {}
            for _lbl, rows, _st in out:
                for cid, nm, _both in rows:
                    known.setdefault(cid, []).append(nm)
            print("=== cross-check: ids used by the scenario plugins ===")
            for c in sorted(mwf_cats):
                names = known.get(c)
                print("  0x%08x  %s" % (c, ", ".join(names) if names
                                       else "(unknown)"))
            print()
            print("  %d of %d resolved" % (sum(1 for c in mwf_cats if c in known),
                                           len(mwf_cats)))

        # and the flat vocabulary, which is mostly pins
        try:
            from scenario_vocab import SCEN, immediates
            flat = {}
            for p in sorted(SCEN.glob("*.so")):
                w, _ = immediates(p)
                for (m, v), n in w.items():
                    if m == "movw" and v >= 0x100:
                        flat[v] = flat.get(v, 0) + n
            pinrows = next((rows for lbl, rows, st in out if st == 16), [])
            if pinrows:
                pinids = {cid for cid, _nm, _b in pinrows}
                hits = sorted(v for v in flat if v in pinids)
                print()
                print("=== the flat 0x0xx/0x1xx/0x2xx vocabulary vs the pin table ===")
                print("  %d distinct immediates; %d are pin ids:" % (len(flat), len(hits)))
                for v in hits:
                    nm = next(nm for cid, nm, _b in pinrows if cid == v)
                    print("    0x%04x  %-22s %d use(s)" % (v, nm, flat[v]))
        except Exception as e:                                # pragma: no cover
            print("pin cross-check skipped: %s" % e)
    except Exception as e:                                # pragma: no cover
        print("cross-check skipped: %s" % e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
