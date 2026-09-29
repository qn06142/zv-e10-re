import os, zlib, struct, re
TOOLS = r"C:\Users\Minhsnguhoa\pmca-re\tools"
data = open(os.path.join(TOOLS, "udtrbody.bin"), "rb").read()
print("size", len(data), "magic", data[:4].hex())

# Try gzip (1f 8b), zlib (78), or raw deflate
def try_decomp(prefix, d):
    try:
        if prefix == "gzip":
            import gzip
            return gzip.decompress(d)
        if prefix == "zlib":
            return zlib.decompress(d)
        if prefix == "raw":
            return zlib.decompress(d, -15)
    except Exception as e:
        return None
    return None

# scan for a compressed stream anywhere
for off in range(0, len(data)-4, 1):
    chunk = data[off:]
    for name, func in (("gzip", lambda c: try_decomp("gzip", c)),
                       ("zlib", lambda c: try_decomp("zlib", c)),
                       ("raw", lambda c: try_decomp("raw", c))):
        out = func(chunk)
        if out and len(out) > 1000:
            # check it's romfs-ish or has our strings
            if b"libupdaterbody.so" in out or b"Compressed ROMFS" in out or b".sh" in out:
                print("DECOMPRESSED @off=0x%x via %s -> %d bytes" % (off, name, len(out)))
                open(os.path.join(TOOLS, "udtrbody_dec.bin"), "wb").write(out)
                # dump interesting strings
                strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{4,}", out)]
                print("strings:", len(strs))
                for s in strs:
                    if any(k in s for k in ("startupdate","endupdate","libupdaterbody","dlopen","bodylib","mount","/tmp_updater","crc","CRC","firm","bodyimg","DllHandler","load","Load")):
                        print("   ", s)
                raise SystemExit
print("no compressed stream found by simple scan")
