import os, re

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
TOOLS = (ROOT_REPO / 'tools').as_posix()
data = open(os.path.join(TOOLS, "adjstctl.elf"), "rb").read()
strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{4,}", data)]
blob = "\n".join(strs)
# usage / help / arg-parsing hints
print("=== usage-like strings ===")
for s in strs:
    if re.search(r"(usage|Usage|USAGE|--|argv|option|command|syntax|example)", s) and len(s) < 200:
        print("  " + s)
print("\n=== strings mentioning 'cmd' as a noun/arg ===")
for s in sorted(set(strs)):
    if re.search(r"\b(cmd|CMD)\b", s) and ("cmd" in s.lower()) and len(s) < 120:
        print("  " + s)
print("\n=== 'exec'/'run'/'system' (command exec?) ===")
for s in sorted(set(strs)):
    if re.search(r"exec|system\(|popen|fork|/bin/|/usr/bin", s, re.I) and len(s) < 120:
        print("  " + s)
print("\n=== first 30 printable strings (often the usage banner) ===")
for s in strs[:30]:
    print("  " + s)
