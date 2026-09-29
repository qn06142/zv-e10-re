"""Parse Sony ZV-E10 /lens/VX*_lensfile.bin ISP calibration tables.

Format (from skill ref zve10-isp-text-segment.md, verified):
  off 0  : 'LF' magic (4c 46)
  off 4  : version uint16 LE (observed 0x0010)
  off 6  : total size uint32 LE (file size)
  off 10 : count uint32 LE (observed 11)
  off 14 : lens_id uint32 LE (e.g. 0x8900)
  off 18 : 'ED' block header (45 44 08 00 ...)
  then   : binary sections, each a descriptor:
             type uint16, count uint16, offset uint32, len uint32
           (e.g. 06 00 | 01 00 | 08 00 00 00 | 1a 00 00 00)
           section bytes live at [offset, offset+len) within the file.

These are the per-lens ISP shading / aberration coefficient arrays.
This is READ-ONLY analysis of already-pulled plaintext files.
"""
import struct, sys, os

def parse(path):
    d = open(path, "rb").read()
    if d[:2] != b"LF":
        return None, "no LF magic (got %r)" % d[:2]
    magic = d[:2]
    version = struct.unpack_from("<H", d, 4)[0]
    size = struct.unpack_from("<I", d, 6)[0]
    count = struct.unpack_from("<I", d, 10)[0]
    lens_id = struct.unpack_from("<I", d, 14)[0]
    # locate the 'ED' block start
    ed = d.find(b"ED\x08\x00", 16)
    info = dict(magic=magic, version=version, size=size, count=count,
                lens_id=hex(lens_id), ed_offset=ed, filesize=len(d))
    sections = []
    # walk section descriptors starting right after the ED header (ed+4)
    p = ed + 4
    while p + 12 <= len(d):
        stype, scount = struct.unpack_from("<HH", d, p)
        soff, slen = struct.unpack_from("<II", d, p + 4)
        if soff + slen > len(d) or soff < ed:
            break
        body = d[soff:soff + slen]
        # try to interpret as int16 LE coefficient array
        vals = []
        if slen >= 2 and slen % 2 == 0:
            vals = list(struct.unpack("<%dh" % (slen // 2), body))
        sections.append(dict(type=stype, count=scount, offset=soff,
                              len=slen, head=body[:16].hex(),
                              int16=vals[:12]))
        p += 12
    info["n_sections"] = len(sections)
    return info, sections

if __name__ == "__main__":
    base = r"C:\Users\Minhsnguhoa\pmca-re\dumps"
    files = [f for f in os.listdir(base) if f.endswith("lensfile.bin")]
    for f in sorted(files):
        info, sections = parse(os.path.join(base, f))
        print("=== %s ===" % f)
        if info is None:
            print("  ", sections); continue
        print("  ", {k: info[k] for k in ("version","size","count","lens_id","ed_offset","n_sections")})
        for s in sections:
            print("   sec type=%d count=%d off=%d len=%d head=%s int16[:12]=%s"
                  % (s["type"], s["count"], s["offset"], s["len"], s["head"], s["int16"]))
