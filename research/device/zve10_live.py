r"""
Live-camera access for the ZV-E10, consolidated behind one command surface.

WHAT THIS IS FOR
----------------
The ZV-E10 exposes three USB personalities and each needs a different driver
binding, because Windows keys the binding on (VID, PID) and the camera re-enumerates
when it changes mode:

    0x0d95  MSC / mass storage   -- the power-on state
    0x0336  senser / service     -- reached via senserShellCommand()'s mode switch
    0x0994  updater              -- documented in docs/LENS_PROTOCOL.md

Binding libusb-win32 (or WinUSB) to one PID does NOT carry over to the others: each
gets a fresh device instance with its own Service value.  Expect to run Zadig once
per PID that you actually intend to use.  Evidence, from the registry:

    Enum\USB\VID_054C&PID_0D95\D0368070BCC4   Service=libusb0
    Enum\USB\VID_054C&PID_0336\5&1d91f5b5&0&3  Service=          <- unbound, Status=Error

The service-mode device is a plain 'libusb0' service, not a filter driver: the USB
class had no LowerFilters/UpperFilters.  Installing the *filter* variant instead
would attach to every USB device on the machine and avoid the per-PID ceremony.

TRAPS THAT COST REAL TIME, ALL OF THEM ENCOUNTERED THE HARD WAY
-------------------------------------------------------------
1. THE TERMINAL IS THE BOTTLENECK, NOT THE CARD.  The SD card writes at ~17.8 MB/s
   and the full 1.45 GB capture takes ~130 s.  What is slow is the MSC->service
   switch plus auth handshake, repeated on every invocation, so batch your commands.

2. /tmp_bt IS A tmpfs.  Any device node or mount point you create there is gone by
   the next session.  mknod AND mount must happen in the SAME command batch as the
   write, or you will silently write into a 1 MB tmpfs and see
   "No space left on device" for a card that is actually 58 GB free.

3. BUSYBOX HERE IS MINIMAL.  v1.34.1 with md5sum/tar/gzip/cut/xxd/mknod/mount, but
   NO `stat` and NO `df`, and the applets are not on PATH as bare commands --
   `md5sum` alone fails, `busybox md5sum` works.  Use `busybox wc -c` for sizes.

4. A VALID FIRST BLOCK PROVES NOTHING.  See research/firmware/fdat_decrypt.py: a
   wrong block size yields a correct UDTRFIRM header and random data after it.

5. `/` IS MOUNTED READ-ONLY, so /dev is read-only and `mknod` fails there.  mknod
   into a tmpfs instead; the node works fine as a mount source.

6. VERIFICATION MUST BE MANDATORY.  `pull` originally did `if cm and ...` around the
   md5 comparison, which silently skipped the check whenever the camera-side
   checksum could not be read -- so a truncated transfer reported success.  It now
   refuses to write an unverified file, and it caught a real 7 MB chunk that would
   otherwise have corrupted the reassembled archive.

7. LONG COMMANDS WRAP IN THE ECHO, they do not corrupt.  A long line echoed back
   across two lines looks like mangling and cost me a wrong diagnosis; the real
   failure was a 120 s timeout, now HARD_TIMEOUT (900 s).

USAGE
-----
    zve10.py scan                what mode is the camera in
    zve10.py shell "cmd" ...     run read-only commands on the service terminal
    zve10.py pull <remote> <out> verified file transfer (<8 MB)
    zve10.py dumpfw [outdir]     capture flash partitions to the SD card
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import subprocess
import sys
import time

# The shared helpers and the repo root have to be importable regardless of cwd.
# senser_fix applies pmca's 0x8000 payload-loss patch on PID 0x0336 -- without it
# bulk reads over the service terminal silently truncate.
_D = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.normpath(os.path.join(_D, "..", "common")),
           os.path.normpath(os.path.join(_D, "..", ".."))):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import senser_fix  # noqa: E402,F401
from pmca.commands.usb import senserShellCommand  # noqa: E402
from pmca.platform.backend.senser import SenserPlatformBackend  # noqa: E402
from zve10_dumpall import _preflight  # noqa: E402

HERE = _D

# Where the camera mounts things, and how big the staging areas really are.
CARD_MOUNT = "/tmp_bt/sd"      # tmpfs mountpoint; the CARD is mounted here
CARD_SUB = "fw_dump"
SCRATCH = "/tmp_bt"            # tmpfs, 1 MB -- mountpoints only, never staging
LOG_PART = "/log"              # nflasha11, vfat, 500 MB -- the real staging area
SMALL_FILE = 8 * 1024 * 1024   # pull ceiling; larger must go via the card

# The card's block device, per /proc/partitions + /sys/block/mmca10p1/dev = 250:11.
CARD_MAJOR, CARD_MINOR = 250, 11

# How long to wait for a command's rc marker before declaring it INCOMPLETE.
HARD_TIMEOUT = 900.0

# Flash partitions worth capturing, and their size in KB from /proc/partitions.
# nflasha8/9/14 do not exist on this model (reserved in partinf.conf).
PARTITIONS = ["1", "2", "3", "4", "5", "6", "7", "10", "11", "12", "13",
              "15", "16", "17", "18", "23", "B0", "B1"]

_SESS: dict = {}


def _p(msg: str) -> None:
    print(msg, flush=True)


def _pump(raw, idle: float = 1.5, hard: float = 300.0, until: str | None = None) -> str:
    """Drain the terminal.  With `until`, ignore the idle break entirely.

    The read window EXTENDS while data keeps arriving (this is what makes a
    multi-second command survive); a fixed window truncates any command whose
    output arrives in bursts.
    """
    buf, last, end = b"", time.time(), time.time() + hard
    while time.time() < end:
        d = raw.readTerminal()
        if d:
            buf += d
            last = time.time()
            end = time.time() + hard
            if until and re.search(until, buf.decode("latin1", "replace")):
                break
        elif until:
            time.sleep(0.05)          # waiting on a marker: never break on silence
        elif time.time() - last > idle:
            break
        else:
            time.sleep(0.01)
    return buf.decode("latin1")


def _sh(raw, cmd: str, idle: float = 1.5, hard: float = 300.0,
        until: str | None = None) -> str:
    raw.writeTerminal(cmd.encode("latin1") + b"\n")
    return _pump(raw, idle, hard, until)


def _md5_on_camera(raw, path: str, tries: int = 3) -> str | None:
    """Camera-side md5, retried.  BusyBox has md5sum but not as a bare command."""
    cmd = "busybox md5sum %s | busybox cut -d' ' -f1" % path
    for _ in range(tries):
        m = re.search(r"\b([0-9a-f]{32})\b", _sh(raw, cmd, 2.0, 60.0))
        if m:
            return m.group(0)
    return None


def _card_ready(raw) -> bool:
    """mknod + mount the SD card.  MUST run in the same batch as any write.

    /tmp_bt is a tmpfs, so a node or mount from an earlier session is gone and the
    write would land in 1 MB of tmpfs instead of the card.
    """
    _sh(raw, "busybox mkdir -p %s %s/%s" % (CARD_MOUNT, CARD_MOUNT, CARD_SUB), 0.5, 20.0)
    _sh(raw, "busybox mknod %s/c b %d %d" % (SCRATCH, CARD_MAJOR, CARD_MINOR), 0.5, 20.0)
    r = _sh(raw, "busybox mount -t vfat %s/c %s" % (SCRATCH, CARD_MOUNT), 2.0, 30.0)
    return CARD_MOUNT in r or "already mounted" in r


# --------------------------------------------------------------- commands --

def _h_scan(dev, rest) -> None:
    out = subprocess.run(
        [sys.executable, os.path.join(HERE, "zve10_replug_gate.py"), "--scan"],
        capture_output=True, text=True, timeout=90).stdout
    _p(out.strip() or "(no Sony device)")
    for pid, name in (("0x0d95", "MSC"), ("0x0336", "service"),
                      ("0x0994", "updater")):
        if pid in out:
            _p("mode: %s (PID %s)" % (name, pid))
            return
    _p("mode: OFF BUS")


def _h_shell(dev, rest) -> None:
    raw = dev.dev
    dev.setTerminalEnable(False)
    dev.setTerminalEnable(True)
    _pump(raw, 2.0)
    raw.writeTerminal(b"\n")
    _pump(raw, 0.5)
    if rest and rest[0] == "-f":
        cmds = [l.strip() for l in open(rest[1])
                if l.strip() and not l.startswith("#")]
    else:
        cmds = rest or ["uname -a"]
    for i, c in enumerate(cmds, 1):
        # Keep every written line SHORT and send the rc marker as its own line.
        # A chained `echo A; cmd; echo B` gets echoed back wrapped, and matching
        # the marker against that echo passes while the real output is missing.
        tag = "Q%d" % i
        rx = r"ZZ%s=(\d+)" % tag
        _p("=== $ %s ===" % c)
        raw.writeTerminal(c.encode("latin1") + b"\n")
        raw.writeTerminal(("echo ZZ%s=$?\n" % tag).encode("latin1"))
        out = _pump(raw, hard=HARD_TIMEOUT, until=rx)
        m = re.search(rx, out)
        if not m:
            _p("!! INCOMPLETE: no ZZ%s= rc within %gs -- do NOT trust the "
               "output above; re-run this command alone." % (tag, HARD_TIMEOUT))
            _pump(raw, 3.0)
        else:
            body = out.split("echo ZZ%s=$?" % tag, 1)[0]
            lines = [l for l in body.splitlines()
                     if l.strip() not in (c.strip(), "echo ZZ%s=$?" % tag)]
            _p("\n".join(lines).rstrip())
            _p("--- rc=%s ---" % m.group(1))
        _pump(raw, 0.3)      # discard anything that trailed the marker
    dev.setTerminalEnable(False)


def _h_pull(dev, rest) -> None:
    remote, out = rest[0], rest[1]
    raw = dev.dev
    dev.setTerminalEnable(False)
    dev.setTerminalEnable(True)
    # BusyBox here has NO `stat`, so the old probe parsed stray digits out of an
    # error string and reported a 1956-byte file as 3616 bytes.  `wc -c` exists.
    m = re.search(r"^\s*(\d+)", _sh(raw, "busybox wc -c < %s" % remote, 1.0, 30.0), re.M)
    sz = int(m.group(1)) if m else None
    _p("remote %s size=%s" % (remote, sz))
    if sz is None:
        _p("!! could not determine size -- refusing to pull")
        dev.setTerminalEnable(False)
        return
    if sz > SMALL_FILE:
        _p("!! file >%d; use dumpfw (SD card) instead" % SMALL_FILE)
        dev.setTerminalEnable(False)
        return
    buf = io.BytesIO()
    dev.readFile(remote, buf)
    data = buf.getvalue()
    # Verification is MANDATORY.  An unverifiable pull is a failed pull.
    cm = _md5_on_camera(raw, remote)
    if not cm:
        _p("!! UNVERIFIED: could not read the camera-side md5 -- not writing")
        dev.setTerminalEnable(False)
        return
    got = hashlib.md5(data).hexdigest()
    if got != cm:
        _p("!! MD5 MISMATCH: camera=%s local=%s (%d B) -- not writing" % (cm, got, len(data)))
        dev.setTerminalEnable(False)
        return
    if len(data) != sz:
        _p("!! SIZE MISMATCH: camera=%d local=%d -- not writing" % (sz, len(data)))
        dev.setTerminalEnable(False)
        return
    with open(out, "wb") as f:
        f.write(data)
    _p("-> %s %d B md5=%s VERIFIED" % (out, len(data), got))
    dev.setTerminalEnable(False)


def _h_dumpfw(dev, rest) -> None:
    """Capture every flash partition onto the SD card, then unmount.

    Writes to the CARD, not to /tmp: /tmp is nflasha10, 12 MB, and filling it is
    what produced a long series of confusing "No space left on device" failures
    against a card with 58 GB free.
    """
    raw = dev.dev
    dev.setTerminalEnable(False)
    dev.setTerminalEnable(True)
    _pump(raw, 2.0)
    if not _card_ready(raw):
        _p("!! SD card unavailable -- is it inserted, and is it FAT32?")
        _p("!! (the camera's kernel has no exFAT driver; see module docstring)")
        dev.setTerminalEnable(False)
        return
    dest = "%s/%s" % (CARD_MOUNT, CARD_SUB)
    _sh(raw, "busybox mkdir -p %s" % dest, 0.5, 20.0)
    for p in PARTITIONS:
        cmd = ("busybox dd if=/dev/nflasha%s of=%s/nflasha%s.img bs=4M 2>/dev/null; "
               "echo P%s=$?" % (p, dest, p, p))
        m = re.search(r"^P%s=(\d+)$" % re.escape(p), _sh(raw, cmd, 2.0, 600.0), re.M)
        rc = m.group(1) if m else "?"
        _p("  nflasha%-3s rc=%s" % (p, rc))
    _sh(raw, "busybox sync", 1.0, 60.0)
    _p(_sh(raw, "busybox ls -l %s" % dest, 2.0, 60.0))
    _sh(raw, "busybox umount %s" % CARD_MOUNT, 1.0, 30.0)
    _p("card unmounted -- safe to remove")
    dev.setTerminalEnable(False)


def _complete(dev) -> None:
    SenserPlatformBackend(dev).start()
    cmd, rest = _SESS["cmd"], _SESS["rest"]
    {"scan": _h_scan, "shell": _h_shell, "pull": _h_pull,
     "dumpfw": _h_dumpfw}[cmd](dev, rest)


USAGE = """usage:
  zve10.py scan
  zve10.py shell "cmd" ["cmd2" ...] | -f file.txt
  zve10.py pull <remote> <out>          (files < 8MB, verified)
  zve10.py dumpfw                       (capture all flash partitions to the SD card)

options:
  --timeout SECONDS   bound the whole session (default 240)
  -r, --retries N     on a wedged handshake, power-cycle the USB device and
                      retry, instead of demanding a manual replug (default 1)
  --no-retry          do not retry; fail immediately
"""


def _recycle_usb() -> bool:
    """Power-cycle the camera's USB device so the next attempt starts clean.

    The wedge is: a session that dies mid-handshake leaves the camera
    enumerating as 0x0336 (service) and half-authenticated.  The next run
    then finds a device that will not complete auth, which is why every
    failure used to cost a manual replug.  Disabling and re-enabling the
    device node forces a re-enumeration from the power-on state (0x0d95).

    Needs the device node to be disable-able, which requires elevation; if
    it is not available the caller falls back to telling the user to replug.
    """
    import subprocess
    devs = [d.InstanceId for d in _pnp_devices()
            if d.InstanceId and d.InstanceId.startswith(r"USB\VID_054C")]
    if not devs:
        return False
    ok = False
    # Hard, SHORT timeouts.  This runs inside the watchdog thread, and the
    # watchdog is the thing that is supposed to bound the session -- a 60 s
    # subprocess here made a 150 s timeout actually take 280 s, which is the
    # opposite of the point.  8 s is ample for a pnputil call.
    for inst in devs:
        for verb, args in (("disable", ["/restart-device"]),
                           ("enable", ["/restart-device"])):
            if verb == "disable":
                args = ["/remove-device"]
            try:
                r = subprocess.run(["pnputil"] + args + [inst],
                                   capture_output=True, text=True, timeout=8)
                _p("  pnputil %-8s -> %s" % (verb, (r.stdout or r.stderr).strip()[:80]))
                ok = ok or r.returncode == 0
            except subprocess.TimeoutExpired:
                _p("  pnputil %-8s -> timed out after 8s" % verb)
            except Exception as e:                        # noqa: BLE001
                _p("  pnputil %-8s -> %s" % (verb, e))
    return ok


def _pnp_devices():
    """Enumerate PnP devices as objects with .InstanceId, via PowerShell."""
    import subprocess
    script = ("Get-PnpDevice -ErrorAction SilentlyContinue | "
              "Where-Object { $_.InstanceId -like '*VID_054C*' } | "
              "Select-Object -ExpandProperty InstanceId")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                           capture_output=True, text=True, timeout=8)
        out = r.stdout
    except Exception:                                    # noqa: BLE001
        return []

    class _D:
        def __init__(self, i):
            self.InstanceId = i
    return [_D(x.strip()) for x in out.splitlines() if x.strip()]


def _run_session(cmd, rest) -> None:
    _SESS["cmd"], _SESS["rest"] = cmd, rest
    senserShellCommand(complete=_complete)   # mode switch + auth, then run


_RETRIES = {"n": 0}


def _watchdog(seconds: int) -> None:
    """Hard wall-clock bound on the whole session.

    senserShellCommand() blocks on a mode switch + auth handshake against a
    device that may be wedged from a previous killed session.  It has no
    internal deadline, so an unresponsive device turns into an indefinite
    CPU spin -- observed burning 821 s of CPU across a 30-minute call.

    On Windows, signal.alarm does not exist, so use a daemon thread and
    os._exit, which also forces the USB handles to be released.
    """
    import threading
    import time

    def _fire():
        _p("")
        _p("=" * 68)
        _p("TIMEOUT after %d s.  The camera did not complete the handshake." % seconds)
        _p("This is the known wedge: a killed session leaves the camera in")
        _p("service mode and the next one cannot authenticate.")
        if _RETRIES["n"] > 0:
            _p("Recycling the USB device and retrying (%d attempt(s) left)..."
               % _RETRIES["n"])
            _RETRIES["n"] -= 1
            if _recycle_usb():
                _p("USB device reset.  Retrying the session.")
                _p("=" * 68)
                sys.stdout.flush()
                time.sleep(8)
                try:
                    _run_session(_SESS["cmd"], _SESS["rest"])
                except Exception as e:                       # noqa: BLE001
                    _p("retry failed: %s" % e)
                    sys.stdout.flush()
                    os._exit(4)
                sys.stdout.flush()
                os._exit(0)
            _p("Could not reset the USB device (needs an elevated shell).")
        _p("FIX: unplug the camera and replug it, then retry.")
        _p("=" * 68)
        sys.stdout.flush()
        os._exit(3)

    # Timer, not Thread: a bare Thread(target=_fire) runs _fire IMMEDIATELY
    # and kills the session instantly, which is not a timeout at all.
    t = threading.Timer(seconds, _fire)
    t.daemon = True
    t.start()


def main(argv: list[str]) -> int:
    # --timeout SECONDS bounds the whole session (default 240)
    # -r/--retries N  power-cycle the USB device and retry on a wedged
    #                 handshake, so a failure no longer costs a manual replug
    timeout = 240
    retries = 1
    rest_all = list(argv)

    def _take(flag):
        nonlocal rest_all
        if flag in rest_all:
            i = rest_all.index(flag)
            if i + 1 >= len(rest_all):
                _p("%s needs a value" % flag)
                return None
            v = rest_all[i + 1]
            del rest_all[i:i + 2]
            return v
        return None

    v = _take("--timeout") or _take("-T")
    if v is not None:
        try:
            timeout = int(v)
        except ValueError:
            _p("--timeout value %r is not an integer" % v)
            return 1
    v = _take("--retries") or _take("-r")
    if v is not None:
        try:
            retries = int(v)
        except ValueError:
            _p("--retries value %r is not an integer" % v)
            return 1
    if "--no-retry" in rest_all:
        rest_all.remove("--no-retry")
        retries = 0

    if not rest_all:
        _p(USAGE)
        return 1
    cmd, rest = rest_all[0], rest_all[1:]
    if cmd not in ("scan", "shell", "pull", "dumpfw"):
        _p(USAGE)
        return 1
    _preflight()
    _RETRIES["n"] = retries
    _p("session watchdog armed: %d s, retries: %d" % (timeout, retries))
    _watchdog(timeout)
    _run_session(cmd, rest)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
