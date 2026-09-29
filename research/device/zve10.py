"""zve10.py -- one CLI for everything ZV-E10.

Consolidates the scattered helper scripts (shell / pull / dump / card) behind a
single command surface so you stop hand-juggling SD cards and tty round-trips.
It AUTO-ROUTES: small files get pulled over USB (readFile); big dumps get dd'd
onto a FAT32 SD card (fastest). Every transfer is md5-checked against the
camera's own busybox md5sum.

Routes:
  zve10.py scan                 what mode is the camera in (MSC / service / off)
  zve10.py gate                 block until a Sony device is on the bus
  zve10.py shell "cmd" ...      run command(s) on the service terminal; -f file
  zve10.py pull <remote> <out>  smart pull (USB readFile; dd-stages if needed)
  zve10.py dump <remote> <out>  big dump -> FAT32 SD card if mounted, else USB
  zve10.py dumpfw [outdir]      dump the 10 /system firmware files (auto-route)

AUTH / MODE SWITCH: the camera starts in MSC (PID 0x0d95). pmca's
senserShellCommand() performs the MSC->service (PID 0x0336) switch AND the
authentication handshake, then calls our complete(dev) with a live terminal.
We MUST go through senserShellCommand -- calling SenserPlatformBackend(dev).
start() alone works only AFTER auth, so it fails on a fresh MSC camera.
This mirrors the proven zve10_shell.py pattern exactly.

All commands import senser_fix (pmca 0x8000 payload-loss patch on PID 0x0336)
and refuse to start if another pmca-re python is alive (_preflight). The USB
session opens only inside senserShellCommand(complete=...) / under __main__,
never at import time.
"""
import sys, os, time, re, io, hashlib, subprocess
import os as _os, sys as _sys; _d = _os.path.dirname(_os.path.abspath(__file__)); _sys.path[:0] = [p for p in (_os.path.normpath(_os.path.join(_d, '..', 'common')),   # shared helpers
                                  _os.path.normpath(_os.path.join(_d, '..', '..'))                                 ) if p not in _sys.path]  # repo root, for `pmca`
import senser_fix  # noqa: F401  -- fixes 0x8000 payload loss on PID 0x0336
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend
from zve10_dumpall import _preflight   # orphan-process guard

CARD_MOUNT = "/tmp/sd"
CARD_SUB   = "fw_dump"
SMALL_FILE = 8 * 1024 * 1024   # below this -> USB pull; above -> SD card (if mounted)

# How long to wait for a command's rc marker before declaring it INCOMPLETE.
# Generous by default: the camera's terminal is slow (a tar of 308 small files
# exceeded 120s), and a false "incomplete" costs a whole re-run.
HARD_TIMEOUT = 900.0

# session state set inside complete(); read by the command handlers
_SESS = {"raw": None, "dev": None}

def _pump(raw, idle=1.5, hard=300.0, until=None):
    """Drain the terminal. If `until` (regex) is given, keep reading until it
    appears (or `hard` elapses) instead of giving up after `idle` of silence.
    Essential for long on-camera work (e.g. a 17MB dd) that's silent for many
    seconds before its result marker prints -- an idle window would cut it off.
    When `until` is set we IGNORE the idle break, otherwise a silent 11s dd
    would trip idle and return before the marker ever prints.

    The read window EXTENDS while data keeps arriving, matching the proven
    pump() in zve10_shell.py.  A fixed window truncates any command whose output
    arrives in bursts.
    """
    import re as _re
    buf, last, end = b"", time.time(), time.time() + hard
    while time.time() < end:
        d = raw.readTerminal()
        if d:
            buf += d; last = time.time()
            end = time.time() + hard          # data flowing -> keep reading
            if until and _re.search(until, buf.decode("latin1", "replace")):
                break
        elif until:
            # waiting for a marker: never break on silence, just keep polling
            time.sleep(0.05)
        elif time.time() - last > idle:
            break
        else:
            time.sleep(0.01)
    return buf.decode("latin1")

def _sh(raw, cmd, idle=1.5, hard=300.0, until=None):
    raw.writeTerminal(cmd.encode("latin1") + b"\n")
    return _pump(raw, idle, hard, until)

def _card_mounted(raw):
    return "YES" in _sh(raw, "busybox mount | busybox grep -q '%s' && echo YES || echo NO" % CARD_MOUNT, 1.0, 20.0)

def _ensure_card(raw):
    if _card_mounted(raw):
        return True
    r = _sh(raw, "busybox mkdir -p %s/%s; busybox mount -t vfat /dev/mmca1 %s; echo MRC=$?"
            % (CARD_MOUNT, CARD_SUB, CARD_MOUNT), 1.0, 30.0)
    return "MRC=0" in r

def _md5_on_camera(raw, path, tries=3):
    """Camera-side md5 of `path`, retried.

    A single 1s-idle read is not reliable on this terminal: the reply sometimes
    arrives late or not at all, and the old code then silently reported "no
    checksum", which -- combined with the `if cm and ...` guard in _h_pull --
    turned an unverifiable transfer into an apparent success.  Retry, and let the
    caller treat a persistent failure as a failed pull.
    """
    cmd = "busybox md5sum %s | busybox cut -d' ' -f1" % path
    for _ in range(tries):
        r = _sh(raw, cmd, 2.0, 60.0)
        m = re.search(r"\b([0-9a-f]{32})\b", r)
        if m:
            return m.group(0)
    return None

# ---------------------------------------------------------------------------
# command handlers -- take the live `dev` (after auth+switch)
# ---------------------------------------------------------------------------
def _h_shell(dev, rest):
    raw = dev.dev
    dev.setTerminalEnable(False); dev.setTerminalEnable(True)
    _pump(raw, 2.0)  # banner
    raw.writeTerminal(b"\n"); _pump(raw, 0.5)
    cmds = ([l.strip() for l in open(rest[1]) if l.strip() and not l.startswith("#")]
            if rest and rest[0] == "-f" else (rest or ["uname -a"]))
    for i, c in enumerate(cmds, 1):
        # The camera terminal mangles LONG written lines: it echoes a command
        # back with the head and/or tail chopped, which is what makes replies
        # look random and incomplete.  So keep every written line short and send
        # the completion marker as its OWN line, never chained with ';'.
        #
        # A separate `echo ZZ<tag>=$?` line reports the previous command's exit
        # code, so "finished" is observable rather than assumed.  Matching the
        # marker against the *echo* of a chained command does NOT work -- the
        # echo contains the literal text, so the check passes while the real
        # output is missing.
        tag = "Q%d" % i
        rx = re.compile(r"ZZ%s=(\d+)" % tag)
        print("=== $ %s ===" % c)
        raw.writeTerminal(c.encode("latin1") + b"\n")
        raw.writeTerminal(("echo ZZ%s=$?\n" % tag).encode("latin1"))
        out = _pump(raw, hard=HARD_TIMEOUT, until=rx.pattern)
        m = rx.search(out)
        if not m:
            print("!! INCOMPLETE: no ZZ%s= rc within %gs -- do NOT trust the"
                  % (tag, HARD_TIMEOUT))
            print("!! output above. The terminal truncated or dropped the line;")
            print("!! re-run this command alone. Draining before continuing.")
            _pump(raw, 3.0)
        else:
            # drop the echo of our own two lines, and the marker itself
            body = out.split("echo ZZ%s=$?" % tag, 1)[0]
            lines = [l for l in body.splitlines()
                     if l.strip() not in (c.strip(), "echo ZZ%s=$?" % tag)]
            print("\n".join(lines).rstrip())
            print("--- rc=%s ---" % m.group(1))
        _pump(raw, 0.3)   # discard anything that trailed the marker
    dev.setTerminalEnable(False)

def _h_pull(dev, rest):
    remote, out = rest[0], rest[1]
    raw = dev.dev
    dev.setTerminalEnable(False); dev.setTerminalEnable(True)
    # BusyBox 1.34.1 here has NO `stat` and NO `df` applet, so the old
    # `busybox stat -c %s` probe returned an error string whose stray digits
    # were then parsed as a size -- which is how a 1956-byte file came to be
    # reported (and transferred) as 3616 bytes.  `wc -c` exists; use it.
    st = _sh(raw, "busybox wc -c < %s" % remote, 1.0, 30.0)
    m = re.search(r"^\s*(\d+)", st, re.M)
    sz = int(m.group(1)) if m else None
    print("remote %s size=%s" % (remote, sz))
    if sz is None:
        print("!! could not determine size (no `wc` reply) -- refusing to pull")
        dev.setTerminalEnable(False); return
    if sz > SMALL_FILE:
        print("!! file >%d; use 'dump' (SD card) instead" % SMALL_FILE)
        dev.setTerminalEnable(False); return
    buf = io.BytesIO()
    dev.readFile(remote, buf)
    data = buf.getvalue()
    # Verification is MANDATORY.  The old `if cm and ...` silently skipped the
    # comparison whenever the camera-side checksum could not be read, so a
    # truncated or padded transfer was reported as success.  An unverifiable
    # pull is a failed pull.
    cm = _md5_on_camera(raw, remote)
    if not cm:
        print("!! UNVERIFIED: could not read the camera-side md5 -- refusing", flush=True)
        print("!! to write an unverified transfer to disk.", flush=True)
        dev.setTerminalEnable(False); return
    got = hashlib.md5(data).hexdigest()
    if got != cm:
        print("!! MD5 MISMATCH: camera=%s local=%s (%d B) -- not writing"
              % (cm, got, len(data)), flush=True)
        dev.setTerminalEnable(False); return
    if len(data) != sz:
        print("!! SIZE MISMATCH: camera=%d local=%d -- not writing"
              % (sz, len(data)), flush=True)
        dev.setTerminalEnable(False); return
    open(out, "wb").write(data)
    print("-> %s %d B md5=%s VERIFIED" % (out, len(data), got))
    dev.setTerminalEnable(False)

def _h_dump(dev, rest):
    remote, out = rest[0], rest[1]
    raw = dev.dev
    dev.setTerminalEnable(False); dev.setTerminalEnable(True)
    if not _ensure_card(raw):
        print("!! SD card not mounted and cannot mount (liro holds it?) -- abort")
        dev.setTerminalEnable(False); return
    dst = "%s/%s/%s" % (CARD_MOUNT, CARD_SUB, os.path.basename(out))
    r = _sh(raw,
        "dd if=%s of=%s bs=512 2>/dev/null; S=$(busybox md5sum %s | busybox cut -d' ' -f1); "
        "D=$(busybox md5sum %s | busybox cut -d' ' -f1); echo CMP S=$S D=$D"
        % (remote, dst, remote, dst), idle=1.0, hard=600.0, until=r"CMP S=[0-9a-f]{32} D=[0-9a-f]{32}")
    m = re.search(r"CMP S=([0-9a-f]{32}) D=([0-9a-f]{32})", r)
    if m and m.group(1) == m.group(2):
        print("OK  %s -> card md5=%s" % (remote, m.group(1)))
    else:
        print("!! dump failed / md5 mismatch")
    dev.setTerminalEnable(False)

FW_FILES = [
    "dfe_dat.bin", "dfe_app.bin", "ldr_drv.bin", "lif_app.bin", "wole_app.bin",
    "bt_firm.hcd", "bonobo.bin", "initrd.img", "vmlinux.bin", "av-cam.bin",
]
def _h_dumpfw(dev, rest):
    outdir = rest[0] if rest else "fw"
    os.makedirs(outdir, exist_ok=True)
    raw = dev.dev
    dev.setTerminalEnable(False); dev.setTerminalEnable(True)
    if not _ensure_card(raw):
        print("!! SD card not mounted; cannot dump (no FAT32 card in camera)")
        dev.setTerminalEnable(False); return
    ok_all = True
    for name in FW_FILES:
        remote = "/system/" + name
        dst = "%s/%s/%s" % (CARD_MOUNT, CARD_SUB, name)
        r = _sh(raw,
            "dd if=%s of=%s bs=512 2>/dev/null; S=$(busybox md5sum %s | busybox cut -d' ' -f1); "
            "D=$(busybox md5sum %s | busybox cut -d' ' -f1); echo CMP S=$S D=$D"
            % (remote, dst, remote, dst), idle=1.0, hard=600.0, until=r"CMP S=[0-9a-f]{32} D=[0-9a-f]{32}")
        m = re.search(r"CMP S=([0-9a-f]{32}) D=([0-9a-f]{32})", r)
        ok = m and m.group(1) == m.group(2)
        ok_all = ok_all and ok
        print("  %-14s %s  %s" % (name, "OK" if ok else "FAIL", m.group(1) if m else "-"))
        if not ok:
            break
    print("ALL OK -> card:%s/%s/" % (CARD_MOUNT, CARD_SUB) if ok_all else "!! incomplete")
    dev.setTerminalEnable(False)

_HANDLERS = {
    "shell": _h_shell, "pull": _h_pull, "dump": _h_dump, "dumpfw": _h_dumpfw,
}

# ---------------------------------------------------------------------------
# entry: senserShellCommand does the MSC->service switch + auth, then calls us
# ---------------------------------------------------------------------------
def _complete(dev):
    # dev is the authenticated service-mode device with a live terminal
    argv = getattr(_complete, "argv", [])
    if not argv:
        print("nothing to do (no subcommand)"); dev.setTerminalEnable(False); return
    cmd, rest = argv[0], argv[1:]
    _HANDLERS[cmd](dev, rest)

def cmd_scan():
    out = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "zve10_replug_gate.py"), "--scan"],
        capture_output=True, text=True, timeout=90).stdout
    print(out.strip() or "(no Sony device)")
    if "0x0d95" in out: print("mode: MSC (PID 0x0d95)")
    elif "0x0336" in out: print("mode: service (PID 0x0336)")
    else: print("mode: OFF BUS")

def cmd_gate():
    rc = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "zve10_replug_gate.py"), "--scan"],
        timeout=600).returncode
    sys.exit(rc)

USAGE = """usage:
  zve10.py scan
  zve10.py gate
  zve10.py shell "cmd" ["cmd2" ...] | -f file.txt
  zve10.py pull <remote> <out>          (files < 8MB)
  zve10.py dump <remote> <out>          (big files -> SD card)
  zve10.py dumpfw [outdir]              (the 10 /system blobs -> SD card)
"""

def main(argv):
    if not argv:
        print(USAGE); return 1
    cmd = argv[0]
    if cmd in ("scan", "gate"):
        {"scan": cmd_scan, "gate": cmd_gate}[cmd]()
        return 0
    if cmd not in _HANDLERS:
        print(USAGE); return 1
    _preflight()  # refuse if another pmca-re python is alive
    _complete.argv = argv
    senserShellCommand(complete=_complete)  # switch + auth, then run cmd
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
