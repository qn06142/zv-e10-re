import os, re, collections

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
FW = (ROOT_REPO / 'fw').as_posix()
av = open(os.path.join(FW, "av-cam.bin"), "rb").read()
strs = [s.decode("latin1", "replace") for s in re.findall(rb'[ -~]{4,}', av)]
blob = " ".join(strs)
uniq = sorted(set(strs))

# 1) CMD_ID_* command surface
cmd_ids = sorted(set(re.findall(r'CMD_ID_[A-Za-z0-9_]+', blob)))
print("=== CMD_ID_* commands (%d) ===" % len(cmd_ids))
for c in cmd_ids:
    print("  " + c)

# 2) Exec* / *Handler / *Msg dispatch symbols
execs = sorted(set(re.findall(r'\b(Exec[A-Za-z0-9_]+)\b', blob)))
handlers = sorted(set(re.findall(r'\b([A-Za-z0-9_]+Handler)\b', blob)))
msgs = sorted(set(re.findall(r'\b([A-Za-z0-9_]*Msg[A-Za-z0-9_]*)\b', blob)))
print("\n=== Exec* symbols (%d) ===" % len(execs))
for e in execs: print("  " + e)
print("\n=== *Handler symbols (%d) ===" % len(handlers))
for h in handlers[:80]: print("  " + h)
print("\n=== *Msg symbols (%d, sample) ===" % len(msgs))
for m in msgs[:60]: print("  " + m)

# 3) SDF sub-commands (the EXEC target family)
sdf = sorted(set(re.findall(r'\bSDF_[A-Za-z0-9_]+\b', blob)))
print("\n=== SDF_* (%d) ===" % len(sdf))
for s in sdf: print("  " + s)

# 4) any "command code" / opcode-style numeric tables?
# look for patterns like CMD + hex or numeric ids near CMD_
opcodes = sorted(set(re.findall(r'(?:CMD|cmd|Command|command)[A-Za-z0-9_]*\s*[:=]\s*(0x[0-9a-fA-F]+|\d+)', blob)))
print("\n=== CMD<->numeric associations (%d) ===" % len(opcodes))
for o in opcodes[:40]: print("  " + o)

# 5) grouping by module prefix to see the dispatch namespaces
prefix = collections.Counter()
for c in cmd_ids:
    parts = c.split("_")
    if len(parts) >= 3:
        prefix["_".join(parts[:2])] += 1
print("\n=== CMD_ID namespace prefixes ===")
for p, n in prefix.most_common():
    print("  %-20s %d" % (p, n))
