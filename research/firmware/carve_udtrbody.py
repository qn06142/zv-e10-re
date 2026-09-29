import os, re
TOOLS = (ROOT_REPO / 'tools').as_posix()
data = open(os.path.join(TOOLS, "udtrbody.bin"), "rb").read()
print("udtrbody.bin:", len(data), "bytes; magic", data[:4].hex())

# 1) Is libupdaterbody.so stored as a raw ELF inside? search ELF magic
elf_magic = b"\x7fELF"
offs = [m.start() for m in re.finditer(re.escape(elf_magic), data)]
print("ELF-magic offsets:", [hex(o) for o in offs])

# 2) search for known romfs/elf/startupdate strings as plaintext
for needle in [b"startupdate.sh", b"libupdaterbody.so", b"\x01\x00\x00\x00", b"#!/", b".sh\x00", b"bodylib", b"udtrbody"]:
    idx = data.find(needle)
    print(f"  {needle!r}: {'@0x%x'%idx if idx>=0 else 'NOT FOUND'}")

# 3) try to carve any ELF we found (first one) and see if it's a valid shared lib
if offs:
    for o in offs[:5]:
        chunk = data[o:o+0x1000]
        # crude: find end by next ELF or size field; just dump header
        print(f"  ELF@0x{o}: {chunk[:16].hex()}")
        open(os.path.join(TOOLS, f"carve_elf_{o:x}.bin"), "wb").write(data[o:o+min(len(data)-o, 200000)])
    print("  carved candidate ELFs -> tools/carve_elf_*.bin")

# 4) entropy of whole file sections to see if ANY part is uncompressed
import math

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
def ent(b):
    if not b: return 0
    from collections import Counter
    c = Counter(b); n = len(b)
    return -sum((v/n)*math.log2(v/n) for v in c.values())
for start in range(0, len(data), 0x4000):
    seg = data[start:start+0x4000]
    e = ent(seg)
    if e < 6.5:
        print(f"  low-entropy segment @0x{start:x}: entropy={e:.2f} (possible uncompressed region)")
