import os, re

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
ROOT = ROOT_REPO.as_posix()
FW = os.path.join(ROOT, "fw")
targets = ["initrd.img", "vmlinux.bin", "bonobo.bin"]
needles = [b"testcmd", b"libosal_uipc", b"CMD_ID_SDF", b"SDF_EXEC", b"osal_uipc",
           b"uipc", b"ExecCmd", b"ExecSensCmd", b"av-cam"]
for t in targets:
    p = os.path.join(FW, t)
    if not os.path.exists(p):
        print("%s: MISSING" % t); continue
    data = open(p, "rb").read()
    print("\n==== %s (%d B) ====" % (t, len(data)))
    hits = {}
    for n in needles:
        c = data.count(n)
        if c:
            hits[n.decode("latin1")] = c
    if not hits:
        print("  (none of the target symbols present)")
    else:
        for k, v in sorted(hits.items(), key=lambda kv: -kv[1]):
            print("  %-14s x%d" % (k, v))
    # if testcmd/uipc present, show a few context snippets
    if "testcmd" in hits or "uipc" in hits:
        for n in (b"testcmd", b"libosal_uipc", b"testcmd_sndmsg"):
            i = data.find(n)
            if i >= 0:
                ctx = data[max(0,i-40):i+len(n)+40]
                print("   ctx[%s]: %s" % (n.decode("latin1"), ctx.replace(b"\x00", b".").decode("latin1","replace")))
