import os, zlib, re
TOOLS = r"C:\Users\Minhsnguhoa\pmca-re\tools"
data = open(os.path.join(TOOLS, "udtrbody.bin"), "rb").read()
print("size", len(data), "magic", data[:4].hex())

# The earlier scan found a zlib stream at 0x17b0 -> 3920 bytes (a small chunk).
# Try: (1) whole-file zlib/gzip/raw at every offset with larger windows,
#       (2) the 0x17b0 stream but allow it to be the header of a longer stream.
def try_dec(name, chunk, wbits):
    try:
        return zlib.decompress(chunk, wbits)
    except Exception:
        return None

best = None
for off in range(0, len(data)-100, 4):
    chunk = data[off:]
    for wbits in (15, -15, 47, 31, -31, 15+16):  # zlib, raw, gzip, large windows
        out = try_dec("x", chunk, wbits)
        if out and len(out) > 5000:
            # prefer outputs containing our known strings
            score = (b"libupdaterbody.so" in out) + (b"startupdate" in out) + (b".sh" in out)
            if best is None or score > best[0]:
                best = (score, off, wbits, out)

if best:
    score, off, wbits, out = best
    print("BEST decompress @0x%x wbits=%d -> %d bytes, score=%d" % (off, wbits, len(out), score))
    open(os.path.join(TOOLS, "udtrbody_dec.bin"), "wb").write(out)
    strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{4,}", out)]
    print("strings:", len(strs))
    for s in strs:
        if any(k in s for k in ("startupdate","endupdate","libupdaterbody","bodylib","dlopen",
                                 "DllHandler","/tmp_updater","crc","CRC","firm","bodyimg",
                                 "load","Load","exec","Exec","update","Update","mount","Mount","firmup")):
            print("   ", s)
else:
    print("no large decompressed stream found (custom Sony compression; raw deflate/zlib/gzip all failed)")
