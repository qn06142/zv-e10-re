import os, re, collections
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM

FW = r"C:\Users\Minhsnguhoa\pmca-re\fw"
av = open(os.path.join(FW, "av-cam.bin"), "rb").read()
N = len(av)

# Pull all printable strings (>=4) - the plaintext treasure map
strs = re.findall(rb'[ -~]{4,}', av)
dec = [s.decode("latin1", "replace") for s in strs]
print("total strings (>=4):", len(dec))

# Group by likely subsystem tokens (Sony module names seen in /proc/modules + earlier bins)
TOKENS = ["DFE","LIF","WoLE","liro","LIRO","backup","Backup","adjst","Adjst",
          "sen","Sen","usb","USB","wlan","bt_","BT_","BT","hdmi","HDMI","cec","CEC",
          "codec","Codec","grm","GRM","upm","UPM","dmm","DMM","stream","Stream",
          "mmc","MMC","ms_","MS_","sircs","SIRCS","mag","Mag","accel","Accel",
          "compass","gyro","lens","Lens","iris","Iris","af_","AF_","ae_","AE_",
          "awb","AWB","face","Face","focus","Focus","zoom","Zoom","shutter","exposure",
          "net","Net","ftp","FTP","http","HTTP","ipc","IPC","uipc","UIPC",
          "cert","Cert","CERT","key","Key","KEY","secure","Secure","SEC","crypt",
          "Crypt","sign","Sign","auth","Auth","version","Ver","diag","Diag","test","Test"]
groups = collections.defaultdict(list)
unclass = []
for s in dec:
    hit = [t for t in TOKENS if t.lower() in s.lower()]
    if hit:
        groups[hit[0]].append(s)
    else:
        unclass.append(s)

print("\n=== subsystem string counts (top matches) ===")
for t in TOKENS:
    if groups.get(t):
        print("  %-8s %4d" % (t, len(groups[t])))

# Show a sample of interesting/unclassified strings: ones containing '/', '()', or error/cmd keywords
print("\n=== sample error/cmd-ish strings (unclassified) ===")
kw = re.compile(r'(error|err|cmd|command|request|set|get|write|read|exec|run|init|open|close|fail|invalid|denied|timeout|version|debug)', re.I)
shown = 0
for s in unclass:
    if kw.search(s) and len(s) < 60:
        print("   ", s[:58]); shown += 1
        if shown >= 40: break

# Look specifically for function-like symbols: "name(" patterns (Sony uses C-style)
print("\n=== function-call-like symbols (name + '(') ===")
funcs = sorted(set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]{2,})\s*\(', " ".join(dec))))
print("  approx function symbols:", len(funcs))
for f in funcs[:50]:
    print("   ", f)

# Path-like strings (/xxx/yyy)
print("\n=== path-like strings ===")
paths = sorted(set(re.findall(r'/[A-Za-z0-9_./-]{3,}', " ".join(dec))))
print("  count:", len(paths))
for p in paths[:40]:
    print("   ", p)
