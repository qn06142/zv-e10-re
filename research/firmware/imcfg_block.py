"""The IMCFG blocks in libObj.so: the device-name table and the id list.

Found by accident, and worth recording how
-----------------------------------------
Searching libObj.so for the message id 0x1001 -- one of the ids recovered from
the scenario plugins -- returned six hits, three of them 20 bytes apart:

    0xe4e35c  0x00001001
    0xe4e370  0x00001002
    0xe4e38c  0x00001005

That spacing is a table, not code. Walking back and forward from it over
plausible ids gives 17 u32 values, and the word right after the last one is
not an id at all -- it is the ASCII `IMFG`... `IMCFG`:

    IMCFG   VER:109 CATEGORY:MAIN TYPE:COM CXD:COM
    /dev/ms  /dev/msa  /dev/msb  /dev/mmca  ...  /dev/nflasha31
    /dev/sd{a,b,c,d}  /dev/sr{0,1}
    /nondev/dvdmenu  /nondev/simulate  /nondev/pcremote  /nondev/air
    /nondev/streaming  /nondev/iptc  /nondev/ipremote

So `libObj.so` carries a build-time configuration block: the message ids the
application registers, and the complete list of device nodes the imaging layer
knows about. That list is the answer to a question the service audit could only
partly answer -- `/dev/nflasha1` .. `/dev/nflasha31` all appear here, plus the
`/nondev/` pseudo-devices that are not devices at all.

There are three `IMCFG` markers in the file and four `CATEGORY:MAIN TYPE:COM
CXD:COM` strings; only the first IMCFG is followed by a device list. The others
are bare or have a different body, so the format is not uniform and this only
claims the block it can actually parse.

Traps here, all silent:
  * The id array ends where a plausible-looking u32 no longer appears. The last
    real id is followed by the first four bytes of the `IMCFG` string, which
    read as 0x46434d49 -- a large number that is not an id. Bounding the walk
    on "looks like an id" stops there, but only by luck of the value.
  * `VER:109` appears three times, so it is a constant in the format string
    rather than a version of this particular block.
"""
import pathlib
import re
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
LIBOBJ = ROOT / "dumps" / "engine" / "libObj.so"

# device-name families, so the table can be grouped rather than listed flat
FAMILIES = [
    ("/dev/ms", "memory stick"),
    ("/dev/mmc", "SD / MMC"),
    ("/dev/sata", "SATA"),
    ("/dev/nflasha", "raw nand A"),
    ("/dev/sd", "SCSI disk"),
    ("/dev/sr", "SCSI CD"),
    ("/nondev/", "pseudo-device (no kernel node)"),
]


def id_array(d, start):
    """Walk out from a known id word while the values keep looking like ids.

    The test has to exclude the first four bytes of the `IMCFG` string that
    terminates the array: `IMCF` reads as 0x46434d49, whose top nibble is 4, so
    a loose "high nibble in 1,2,3,4,6,8" test accepts it and the array comes out
    with a 1.1-billion entry in it.  Two guards: a sane ceiling, and a check
    that the bytes at that address really are the marker.
    """
    def ok(w, off):
        if not (0x100 <= w <= 0x8FFFF):
            return False
        if (w >> 12) not in (0x1, 0x2, 0x3, 0x4, 0x6, 0x8):
            return False
        # the array ends where the ASCII marker begins
        return d[off:off + 4] != b"IMCF"
    lo = start
    while lo - 4 >= 0 and ok(struct.unpack_from("<I", d, lo - 4)[0], lo - 4):
        lo -= 4
    hi = start
    while hi + 4 <= len(d) and ok(struct.unpack_from("<I", d, hi)[0], hi):
        hi += 4
    # hi is the first word that FAILED, so it is not part of the array.  The
    # backward walk leaves lo on the first included word, which makes the two
    # ends inconsistent: taking (hi - lo)//4 + 1 includes the rejected word and
    # put 0x46434d49 ("IMCF") in the list.  Step hi back to the last good word.
    last = hi
    if last > start:
        last -= 4
    return [struct.unpack_from("<I", d, lo + 4 * i)[0]
            for i in range((last - lo) // 4 + 1)]


def main():
    if not LIBOBJ.exists():
        print("missing %s" % LIBOBJ)
        return 1
    d = LIBOBJ.read_bytes()
    print("libObj.so  %d bytes\n" % len(d))

    markers = [m.start() for m in re.finditer(rb"IMCFG", d)]
    print("IMCFG markers: %d at %s\n" % (len(markers),
                                         " ".join(hex(x) for x in markers)))

    for mi, mo in enumerate(markers):
        end = d.find(b"\x00", mo)
        head = d[mo:end].decode("latin1", "replace")
        print("--- IMCFG #%d at 0x%08x ---" % (mi, mo))
        print("    %s" % head)
        # the device list follows the header, NUL-separated
        devs = []
        p = end + 1
        while p < len(d):
            q = d.find(b"\x00", p)
            if q < 0:
                break
            s = d[p:q]
            if not s:
                p = q + 1
                if devs:
                    break
                continue
            try:
                t = s.decode("ascii")
            except UnicodeDecodeError:
                break
            if not (t.startswith("/dev/") or t.startswith("/nondev/")):
                break
            devs.append(t)
            p = q + 1
        if not devs:
            print("    (no device list follows this marker)")
            print()
            continue
        print("    %d device names:" % len(devs))
        for fam, desc in FAMILIES:
            hits = [x for x in devs if x.startswith(fam)]
            if hits:
                print("      %-14s %-32s %2d  %s .. %s"
                      % (fam, desc, len(hits), hits[0], hits[-1]))
        odd = [x for x in devs
               if not any(x.startswith(f) for f, _ in FAMILIES)]
        if odd:
            print("      unclassified: %s" % ", ".join(odd))
        print()

    # the id list, anchored on the first marker and walked back over it
    m0 = markers[0]
    seed = None
    for back in range(0, 0x400, 4):
        o = m0 - back
        w = struct.unpack_from("<I", d, o)[0]
        if w == 0x1001:
            seed = o
            break
    if seed is None:
        print("could not locate the id array")
        return 1
    ids = id_array(d, seed)
    print("--- message id array immediately before IMCFG #0 ---")
    print("    %d ids: %s" % (len(ids), " ".join("0x%04x" % x for x in ids)))
    uniq = sorted(set(ids))
    print("    %d distinct, range 0x%04x..0x%04x"
          % (len(uniq), uniq[0], uniq[-1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
