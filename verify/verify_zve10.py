
"""Ad-hoc offline verification for the ZV-E10 helper scripts (no camera needed).

Kept in-repo (not %TEMP%) so the evidence survives; run:
    .venv/Scripts/python.exe verify/verify_zve10.py
Covers the two behaviours that are easy to get silently wrong:
  pump()  -- tty drain timing (a too-short quiet window reads success as silence)
  dumpall -- dd chunk tiling / resume offsets (a bad skip corrupts a 1.4GB dump)
"""
import sys, os, types, tempfile, importlib, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_u = types.ModuleType("pmca.commands.usb")
_u.senserShellCommand = lambda complete=None, **kw: None
sys.modules["pmca.commands.usb"] = _u
_b = types.ModuleType("pmca.platform.backend.senser")
_b.SenserPlatformBackend = lambda dev: types.SimpleNamespace(start=lambda: None)
sys.modules["pmca.platform.backend.senser"] = _b

fails = []
def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (("  " + extra) if extra and not cond else ""))
    if not cond: fails.append(name)

tmp = tempfile.mkdtemp(prefix="hermes-verify-zve10-"); os.chdir(tmp)
def load(name, argv):
    sys.argv = [name] + argv
    for m in [m for m in sys.modules if m.startswith("zve10_")]: del sys.modules[m]
    return importlib.import_module(name)

class Tty:
    """Fake terminal: emits scripted (delay, data), then silence."""
    def __init__(self, script): self.s, self.t0 = list(script), time.time()
    def readTerminal(self):
        if self.s and time.time() - self.t0 >= self.s[0][0]: return self.s.pop(0)[1]
        return b""

# ---------------- zve10_shell.py ----------------
os.environ["ZVE10_LOG"] = os.path.join(tmp, "t.log")
cf = os.path.join(tmp, "c.txt"); open(cf, "w").write("uname -a\n\n# note\ncat /proc/mtd\n  \n")
check("shell -f strips blanks+comments",
      load("zve10_shell", ["-f", cf]).CMDS == ["uname -a", "cat /proc/mtd"])
check("shell positional args", load("zve10_shell", ["id"]).CMDS == ["id"])
sh = load("zve10_shell", [])
check("shell defaults", len(sh.CMDS) == 3)
sh.out("\n".join("l%d" % i for i in range(200)))
check("out() logs full text", open(sh.LOG, encoding="latin1").read().count("\n") >= 200)

check("pump waits through a 1.0s stall", b"late" in sh.pump(Tty([(1.0, b"late\n")]), seconds=4.0))
check("pump accumulates bursts",
      sh.pump(Tty([(0.1, b"a"), (0.6, b"b"), (1.2, b"c")]), seconds=5.0) == b"abc")
t0 = time.time(); sh.pump(Tty([]), seconds=10.0)
check("pump returns on silence", time.time() - t0 < 4.0)
# the test must discriminate: the OLD 0.6s window has to miss the stalled reply
check("stall test discriminates vs old 0.6s window",
      b"late" not in sh.pump(Tty([(1.0, b"late\n")]), seconds=4.0, quiet_after=0.6))

# ---------------- zve10_dumpall.py ----------------
m = load("zve10_dumpall", [])
# The old 0xF8000 "cap" was a misdiagnosis: the real bug was pmca's bogus
# 512-byte padding read on PID 0x0336 (fixed in senser_fix.py). Chunks are now
# sized for THROUGHPUT -- tty round-trips dominate, so bigger is better.
check("chunk is large enough to amortize tty round-trips",
      m.CHUNK >= 8 * 1024 * 1024, "%d" % m.CHUNK)
check("chunk 512-aligned", m.CHUNK % 512 == 0)
check("stage is on the big /log partition", m.STAGE.startswith("/log/"), m.STAGE)
# staging into the partition you're reading would corrupt the dump
check("/log dump does NOT stage into /log",
      not m.STAGE_CONFLICT["/dev/nflasha11"][0].startswith("/log/"))
check("/tmp dump does NOT stage into /tmp",
      not m.STAGE_CONFLICT["/dev/nflasha10"][0].startswith("/tmp/"))
check("/log conflict chunk fits in 12MB /tmp",
      m.STAGE_CONFLICT["/dev/nflasha11"][1] <= 12 * 1024 * 1024)
check("partition sizes 512-aligned", not [n for n, d, s in m.TABLE if s % 512])
names = [n for n, _, _ in m.TABLE]; devs = [d for _, d, _ in m.TABLE]
check("no dup names/devices", len(set(names)) == len(names) and len(set(devs)) == len(devs))
check("small partitions first", names.index("nflasha7_rootfs") < names.index("nflasha15_usr"))

def plan(size, chunk, start=0):
    steps, done = [], start
    while done < size:
        n = min(chunk, size - done); steps.append((done // 512, n // 512, n)); done += n
    return steps, done

for size in (8192 * 1024, 61440 * 1024, 2048 * 1024):
    steps, end = plan(size, m.CHUNK)
    off, ok = 0, True
    for skip, cnt, n in steps:
        if skip * 512 != off or cnt * 512 != n: ok = False; break
        off += n
    check("tiles %dB exactly, contiguous" % size, end == size and ok and off == size)
steps, end = plan(8192 * 1024, m.CHUNK, start=512 * 1024)
check("resume at correct block, exact end", steps[0][0] == 1024 and end == 8192 * 1024)

# ---------------- import safety (regression) ----------------
# Every script must guard senserShellCommand behind __main__. Without it,
# merely importing a module opens a USB session and burns the camera's
# single-session-per-plug budget (this actually happened: importing
# zve10_dumpall ran the entire 18-partition table and killed the session).
import re as _re
for _f in ("zve10_shell.py", "zve10_pull.py", "zve10_dump.py", "zve10_dumpall.py"):
    _src = open(os.path.join(ROOT, _f), encoding="utf-8").read()
    # the guard may contain other setup lines (e.g. _preflight()) before the call
    _blk = _re.search(r'if __name__ == ["\']__main__["\']:\n((?:[ \t]+\S.*\n?)+)', _src)
    check("%s guards senserShellCommand behind __main__" % _f,
          bool(_blk) and "senserShellCommand" in _blk.group(1))
    check("%s has no top-level senserShellCommand call" % _f,
          not _re.search(r'^senserShellCommand\(', _src, _re.M))

# the dumper must refuse to run alongside a stale pmca-re python (orphaned
# background children keep the USB session pinned and wedge the camera)
_dsrc = open(os.path.join(ROOT, "zve10_dumpall.py"), encoding="utf-8").read()
check("dumpall preflights for stale pmca-re processes",
      "_preflight()" in _dsrc and "REFUSING TO START" in _dsrc)

# ---------------- sample_isp.py (firmware sampling) ----------------
_s = load("sample_isp", [])
_ssrc = open(os.path.join(ROOT, "sample_isp.py"), encoding="utf-8").read()
# real file sizes from `ls -la /system` on the camera
_SZ = {"/system/av-cam.bin": 17289388, "/system/vmlinux.bin": 4117760,
       "/system/bonobo.bin": 172144, "/system/dfe_dat.bin": 65536,
       "/system/initrd.img": 2183168}
check("samples never read past EOF",
      not [(l, sk, c) for l, src, sk, c in _s.SAMPLES if (sk + c) * 512 > _SZ[src]],
      repr([(l, sk, c) for l, src, sk, c in _s.SAMPLES if (sk + c) * 512 > _SZ[src]]))
check("sample labels unique", len({l for l, _, _, _ in _s.SAMPLES}) == len(_s.SAMPLES))
check("samples stay small (<=64KB, fit /tmp)", all(c * 512 <= 65536 for _, _, _, c in _s.SAMPLES))
# an entropy verdict is meaningless without a known-plaintext baseline
check("includes vmlinux known-plaintext control", any("vmlinux" in l for l, _, _, _ in _s.SAMPLES))
check("probes av-cam at >=3 offsets", len({sk for l, _, sk, _ in _s.SAMPLES if "avcam" in l}) >= 3)
# this is the user's WORKING camera: sampling must never write to it
check("sampling is read-only",
      not any(w in _ssrc for w in ("writeFile", "of=/dev/", "> /dev/nflash", "writeBackup")))

print("\nRESULT:", "ALL PASS" if not fails else "FAILURES: %s" % fails)
sys.exit(1 if fails else 0)
