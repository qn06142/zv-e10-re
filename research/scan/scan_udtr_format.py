import os, sys, io
ROOT = ROOT_REPO.as_posix()
REPO = os.path.join(ROOT, "fwtool_ma1co_repo")
UDT = os.path.join(ROOT, "tools", "udtrbody.bin")
sys.path.insert(0, REPO)

data = open(UDT,"rb").read()
print("udtrbody.bin size", len(data), "magic", data[:4].hex())

# Try fwtool's archive/compression decoders on it
mods = {
 "gz": "fwtool.archive.gz",
 "lzh": "fwtool.lzh",
 "lz77": "fwtool.lz77",
 "cramfs": "fwtool.archive.cramfs",
 "squashfs": "fwtool.archive.squashfs",
 "lzpt": "fwtool.archive.lzpt",
 "tar": "fwtool.archive.tar",
 "cpio": "fwtool.archive.cpio",
 "fat": "fwtool.archive.fat",
 "ext2": "fwtool.archive.ext2",
 "axfs": "fwtool.archive.axfs",
}
for name, mod in mods.items():
    try:
        m = __import__(mod, fromlist=["is"+name.capitalize() if False else "is"+name[0].upper()+name[1:]])
    except Exception as e:
        print("  skip", name, "(import)", e); continue
    try:
        fn = getattr(m, [a for a in dir(m) if a.lower().startswith("is")][0])
        ok = fn(io.BytesIO(data))
        print("  %-10s is%s? %s" % (name, fn.__name__, ok))
    except Exception as e:
        print("  %-10s err: %s" % (name, e))

# Also: ROMFS heuristic - file entries are 16-byte aligned; try to find readable
# filename strings + their following data. ROMFS node = 16B header then name\0.
import re

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{4,}", data)]
# the known filenames
for fn in ["libupdaterbody.so","startupdate.sh","body_common.sh","pformat.elf","chkfirm.sh"]:
    idx = data.find(fn.encode())
    print("  %s @0x%x" % (fn, idx))
