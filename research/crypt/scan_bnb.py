import os, re

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
ROOT = (ROOT_REPO / 'fw').as_posix()
data = open(os.path.join(ROOT, "av-cam.bin"), "rb").read()
strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{4,}", data)]
txt = data.decode("latin1","replace")

# All BNB / SelfFlash / update-trigger context
print("=== BNB / SelfFlash / Recovery strings ===")
for s in sorted(set(strs)):
    if re.search(r"BNB|SelfFlash|self_flash|RECOVER|recover|UPDAT|updat|firmup|FirmUp|"
                 r"bodyimg|udtr|UDTR|ExtFl|ext_fl|/android/storage|sdcard", s, re.I):
        print("  " + s)

# Context around the first BNB occurrence
m = re.search(rb"BNB_", data)
if m:
    off = m.start()
    print("\n=== bytes around first BNB (0x%X) ===" % off)
    ctx = data[max(0,off-200):off+200]
    print(ctx.decode("latin1","replace"))

# Any osal_id / function that mentions BNB or self-flash (symbol-ish)
print("\n=== likely update functions (Update/Flash/Firm/Recover in names) ===")
for s in sorted(set(strs)):
    if re.match(r"[A-Za-z_]*[Uu]pdate[A-Za-z_]*$|[A-Za-z_]*[Ff]lash[A-Za-z_]*$"
                r"|[A-Za-z_]*[Rr]ecover[A-Za-z_]*$|[A-Za-z_]*[Ff]irm[A-Za-z_]*$", s):
        print("  " + s)
