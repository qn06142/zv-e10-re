import os, re
ROOT = r"C:\Users\Minhsnguhoa\pmca-re"
bins = open(os.path.join(ROOT, "bin.txt")).read().splitlines()
apps = open(os.path.join(ROOT, "app.txt")).read().splitlines()
allb = bins + apps
print("total binaries:", len(allb))

pat = re.compile(r"(cmd|test|exec|shell|ctl|svc|srv|diag|adj|cal|tune|set|get|tool|util|main|mon|proxy|upd|firm|ipc|msg|snd|rcv|boot|rom|key|auth|secure|sign|verif|load|init|conf|cfg|param|oreg|adjust|meas)", re.I)
hits = sorted(set(b for b in allb if pat.search(b)))
print("\n=== interesting-by-name (%d) ===" % len(hits))
for h in hits:
    print("  " + h)

# ELF vs script? list ones that look like real tools (not busybox links)
print("\n=== all /usr/bin (50) ===")
for b in bins:
    print("  " + b)
