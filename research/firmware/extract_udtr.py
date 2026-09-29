import os, sys, io
ROOT = ROOT_REPO.as_posix()
REPO = os.path.join(ROOT, "fwtool_ma1co_repo")
UDT = os.path.join(ROOT, "tools", "udtrbody.bin")
OUT = os.path.join(ROOT, "udtrbody_extract")
sys.path.insert(0, REPO)

data = open(UDT,"rb").read()
print("size", len(data), "magic", data[:4].hex())

from fwtool.archive import cramfs as C

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
with open(UDT,"rb") as f:
    gen = C.readCramfs(f)
    os.makedirs(OUT, exist_ok=True)
    n = 0
    for u in gen:
        rel = u.path.lstrip("/")
        if u.path in ("", "/"):  # skip root dir entry name
            continue
        dst = os.path.join(OUT, rel)
        if u.contents is None:
            os.makedirs(dst, exist_ok=True)
            print("DIR ", rel)
        else:
            os.makedirs(os.path.dirname(dst) or OUT, exist_ok=True)
            u.contents.seek(0)
            open(dst,"wb").write(u.contents.read())
            print("FILE", rel, os.path.getsize(dst), "B")
            n += 1
    print("extracted", n, "files ->", OUT)
