
"""Run commands on the ZV-E10's service-mode Linux terminal.

pmca's `shell` command relays a socket to stdin, which is useless from an
agent. This talks to dev.readTerminal()/writeTerminal() directly.

usage: zve10_shell.py "uname -a" "cat /proc/cpuinfo" ...
"""
import sys, os, time
import os as _os, sys as _sys; _d = _os.path.dirname(_os.path.abspath(__file__)); _sys.path[:0] = [p for p in (_os.path.normpath(_os.path.join(_d, '..', 'common')),   # shared helpers
                                  _os.path.normpath(_os.path.join(_d, '..', '..'))                                 ) if p not in _sys.path]  # repo root, for `pmca`
import senser_fix  # noqa: F401  -- fixes 0x8000 payload loss on PID 0x0336
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend

_a = sys.argv[1:]
if len(_a) == 2 and _a[0] == "-f":
    CMDS = [l.strip() for l in open(_a[1]) if l.strip() and not l.startswith("#")]
else:
    CMDS = _a or ["uname -a", "id", "ls -la /"]

LOG = os.environ.get("ZVE10_LOG", "zve10_shell.log")
_logf = open(LOG, "w", encoding="latin1", newline="")
def out(s=""):
    """Print to console AND log; console output is capped so a huge listing
    can't push earlier results out of a tail window."""
    _logf.write(s + "\n"); _logf.flush()
    lines = s.split("\n")
    if len(lines) > 25:
        s = "\n".join(lines[:12] + ["   ... [%d lines omitted, see %s] ..." % (len(lines)-24, LOG)] + lines[-12:])
    print(s, flush=True)

def pump(dev, seconds=2.0, quiet_after=1.5):
    """Drain the terminal until it goes quiet."""
    buf = b""
    last = time.time()
    end = time.time() + seconds
    while time.time() < end:
        d = dev.readTerminal()
        if d:
            buf += d
            last = time.time()
            end = time.time() + seconds   # extend while data flows
        elif time.time() - last > quiet_after:
            break
        else:
            time.sleep(0.02)
    return buf

def complete(dev):
    SenserPlatformBackend(dev).start()
    raw = dev.dev
    dev.setTerminalEnable(False)
    dev.setTerminalEnable(True)
    try:
        banner = pump(raw, 3.0)
        if banner:
            out("--- banner ---")
            out(banner.decode("latin1"))
        raw.writeTerminal(b"\n")
        pump(raw, 1.0)
        for c in CMDS:
            out("\n===== $ %s =====" % c)
            raw.writeTerminal(c.encode("latin1") + b"\n")
            out(pump(raw, 6.0).decode("latin1"))
    finally:
        dev.setTerminalEnable(False)

if __name__ == "__main__":
    senserShellCommand(complete=complete)
