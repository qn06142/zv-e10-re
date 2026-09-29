import subprocess, os, time

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]

names = [l.strip() for l in open((ROOT_REPO / 'dumps/lenslist.txt').as_posix(), encoding="latin1") if l.strip()]
outdir = (ROOT_REPO / 'dumps/lens').as_posix()
os.makedirs(outdir, exist_ok=True)

def pull_one(remote, local):
    for attempt in range(8):
        try:
            r = subprocess.run(["./.venv/Scripts/python.exe","zve10_pull.py",remote],
                                capture_output=True, text=True, timeout=90,
                                cwd=ROOT_REPO.as_posix())
            if os.path.exists(local) and os.path.getsize(local) > 0:
                return True
        except Exception:
            pass
        time.sleep(0.4)
    return False

ok = 0
for n in names:
    remote = "/log/lens_" + n
    local = os.path.join(outdir, n)
    if os.path.exists(local) and os.path.getsize(local) > 0:
        ok += 1
        continue
    if pull_one(remote, local):
        ok += 1
        print("OK %s" % n, flush=True)
    else:
        print("FAIL %s" % n, flush=True)
print("DONE: %d/%d pulled" % (ok, len(names)))
