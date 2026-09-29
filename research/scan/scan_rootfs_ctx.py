import os, re

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
ROOT = ROOT_REPO.as_posix()
data = open(os.path.join(ROOT, "fw", "initrd.img"), "rb").read()
for n in (b"uipc", b"osal_uipc"):
    print("=== context for %r ===" % n)
    start = 0
    cnt = 0
    while True:
        i = data.find(n, start)
        if i < 0: break
        ctx = data[max(0,i-50):i+len(n)+50]
        print("  " + ctx.replace(b"\x00", b".").decode("latin1","replace"))
        start = i + 1
        cnt += 1
        if cnt >= 4: break
# also: is initrd.img a compressed fs? check magic
print("\n=== initrd magic ===")
print("gzip:", data[:2] == b"\x1f\x8b", "lzma:", data[:5] == b"\xfd7zXZ", "cpio:", data[:6] in (b"070701", b"070702"))
