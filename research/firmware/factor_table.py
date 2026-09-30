"""The DefInh factor table in libSysDef.so -- 3948 records of 800 bytes.

Found while answering "what RE is left offline".  libSysDef.so is 3.2 MB and
96.7% of it is this one exported data symbol:

    DefInh::sm_refTbl   3,158,400 bytes

The geometry is not documented anywhere and was recovered from the two
accessors the library exports, which are the only clue to it:

    DefInh::GetFactorIdMax()    -> movw r0, #0x18fd   = 6381   factor ids
    DefInh::GetFactorTblMax()  -> movs r0, #0xc8     = 200    table slots

Neither divides the size, so both are red herrings for the layout -- 6381 is a
count of ids, 200 a count of slots, and neither is the record count:

    3,158,400 / 800 = 3948    exactly

800 is the stride, and it is visible directly in the data: the first non-zero
byte after the table's leading word sits at +0x320, then +0x640, then +0x960 --
gaps of exactly 0x320.  And the non-zero bytes cluster at a small set of
residues mod 800 (around 301-302, 360-361, 369-370, 404-405, 551), which is
what a fixed-stride array of mostly-zero records looks like.

Record shape, from the first two records:

    +0     u32   1 in record 0, 0x002023f6 in record 1
    +160   s24:hi  0xffe00000 / 0x001fffff
    +164   s24:lo  ... i.e. a signed 24-bit value split across two words
    +196   u32   0x20
    +312   u32   0x1c

The +160/+164 pair is the interesting one: 0xffe00000 and 0x001fffff are
adjacent 24-bit values (-0x200000 and +0x1fffff), which is the signature of a
A first guess was that +160/+164 is a signed 24-bit min/max pair -- 0xffe00000
and 0x001fffff are adjacent 24-bit values (-0x200000 and +0x1fffff), which
looks like a normalised fixed-point range.  **That is wrong.**  Records 39..44
put 0x01000000/1, 0x02000000/2, 0x04000000/4 ... in those two words: a
doubling sequence, not a range.  The fields are independent, and the table is
sparse enough that any two adjacent non-zero words invite a pattern that is
not there.  Reading them as a pair is an artefact of looking at record 1 alone.

What the fields actually look like: 24 offsets are in use across the table, and
none dominates -- the most common (+548) appears in 20.5% of records and the
24th (+644) in 10.4%.  With 88% of records populated and no field above 21%,
this reads as a tagged union: a factor record carries a handful of values
selected by whatever kind of factor it is, rather than a fixed struct.  Naming
the fields needs the index that maps a factor id to a record, and that is what
GetFactorIdMax (6381 ids) is for -- it does not divide the record count, which
fits an id-to-record indirection rather than a direct array.

The distribution of fields-per-record is bimodal, which is what a union would
give: 1,610 records carry exactly one non-zero word, then the count thins to a
minimum around 40 and rises again to a second cluster at 64-70 fields, with one
record at the full 200 (i.e. every word non-zero -- probably a memset default
or an "all factors valid" marker).  So there are at least two record shapes:
a small scalar kind, and a bulk kind with 64+ values.  That is consistent with
a camera adjustment table where some factors are one number (a gain, an offset)
and others are a per-sensor or per-mode block of 64+ values.

So: geometry recovered, semantics not.  This is a camera adjustment table, a
different axis from everything in 04-messaging.md and
04-messaging.md.
"""
import collections
import pathlib
import struct
import sys

from elftools.elf.elffile import ELFFile

ROOT = pathlib.Path(__file__).resolve().parents[2]
SYSDEF = ROOT / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libSysDef.so"

STRIDE = 800


def load(path=SYSDEF):
    p = pathlib.Path(path)
    data = p.read_bytes()
    f = ELFFile(open(p, "rb"))
    segs = [s for s in f.iter_segments()
            if s["p_type"] == "PT_LOAD" and s["p_filesz"]]
    tbl = None
    ds = f.get_section_by_name(".dynsym")
    for s in ds.iter_symbols():
        if s.name and s.name.endswith("sm_refTblE") and s["st_size"]:
            for seg in segs:
                if seg["p_vaddr"] <= s["st_value"] < seg["p_vaddr"] + seg["p_filesz"]:
                    tbl = seg["p_offset"] + (s["st_value"] - seg["p_vaddr"])
                    size = s["st_size"]
    return data, f, segs, tbl, size


def records(data, tbl, size):
    n = size // STRIDE
    for i in range(n):
        yield i, data[tbl + i * STRIDE : tbl + (i + 1) * STRIDE]


def fields(rec):
    """Non-zero u32 fields of one record, as (offset, value)."""
    out = []
    for k in range(0, len(rec) - 3, 4):
        w = struct.unpack_from("<I", rec, k)[0]
        if w:
            out.append((k, w))
    return out


def main():
    if not SYSDEF.exists():
        print("missing %s" % SYSDEF)
        return 1
    data, f, segs, tbl, size = load()
    if tbl is None:
        print("sm_refTbl not found")
        return 1

    n = size // STRIDE
    print("libSysDef.so  %d bytes" % len(data))
    print("DefInh::sm_refTbl at file offset 0x%x, %d bytes" % (tbl, size))
    print()
    print("  stride %d  ->  %d records   (%d %% of the file)"
          % (STRIDE, n, round(100.0 * size / len(data), 1)))
    print("  exact division: %s" % (size % STRIDE == 0))
    print()

    # which offsets are ever used?
    used = collections.Counter()
    populated = 0
    firstid = 0
    for i, rec in records(data, tbl, size):
        fs = fields(rec)
        if i == 0 and fs and fs[0][0] == 0:
            firstid = fs[0][1]
        if fs:
            populated += 1
        for k, _v in fs:
            used[k] += 1

    print("  populated records: %d of %d (%.1f%%)"
          % (populated, n, 100.0 * populated / n))
    print("  leading word of record 0: %d  (likely a version or table id)" % firstid)
    print()
    print("  field offsets in use (offset: records using it):")
    for k, c in used.most_common(24):
        print("    +%-4d  %6d  (%.1f%% of records)" % (k, c, 100.0 * c / n))
    print()

    print("  first six populated records:")
    shown = 0
    for i, rec in records(data, tbl, size):
        fs = fields(rec)
        if not fs:
            continue
        print("    [%4d] %s" % (i, "  ".join("+%d=0x%x" % (k, v) for k, v in fs)))
        shown += 1
        if shown >= 6:
            break
    print()

    # the +160/+164 pair, wherever present, read as a signed 24-bit range
    print("  +160/+164 pairs, first 12 records that have them:")
    shown = 0
    for i, rec in records(data, tbl, size):
        if len(rec) < 168:
            continue
        hi = struct.unpack_from("<I", rec, 160)[0]
        lo = struct.unpack_from("<I", rec, 164)[0]
        if not (hi or lo):
            continue
        print("    [%4d]  hi=0x%08x  lo=0x%08x   (as signed 32: %d / %d)"
              % (i, hi, lo, struct.unpack("<i", struct.pack("<I", hi))[0],
                 struct.unpack("<i", struct.pack("<I", lo))[0]))
        shown += 1
        if shown >= 12:
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
