import struct, os

base = r"C:\Users\Minhsnguhoa\pmca-re\dumps"
for f in ["VX8900_lensfile.bin","VX9101_lensfile.bin"]:
    d = open(os.path.join(base,f),"rb").read()
    print("=== %s (size=%d) ===" % (f, len(d)))
    print("  head:", d[:32].hex())
    # header per real bytes: LF[0:2] ver[2:4] size[4:8] count[8:12] lens[12:16] ED[16:20]
    ver = struct.unpack_from("<H", d, 2)[0]
    size = struct.unpack_from("<I", d, 4)[0]
    cnt = struct.unpack_from("<I", d, 8)[0]
    lens = struct.unpack_from("<I", d, 12)[0]
    print("  ver=%d size=%d count=%d lens_id=0x%x" % (ver, size, cnt, lens))
    # ED header at 16: 'ED' + u16 len?
    print("  [16:24]:", d[16:24].hex())
    # walk 12-byte descriptors from 24
    p = 24
    i = 0
    while p + 12 <= len(d):
        t, c, off, ln = struct.unpack_from("<HHII", d, p)
        print("   desc[%d] @%d: type=%d count=%d off=%d len=%d  raw=%s  off+len=%d (filesize=%d) %s"
              % (i, p, t, c, off, ln, d[p:p+12].hex(), off+ln, len(d),
                 "OK" if off+ln <= len(d) else "OOB"))
        p += 12
        i += 1
        if i > 20: break
    print()
