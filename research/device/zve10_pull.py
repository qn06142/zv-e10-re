"""Pull files/partitions off the ZV-E10 using pmca's native file protocol
(SONY_FILE_CONTROL_READ) -- far faster and more reliable than base64 over tty.

usage: zve10_pull.py <remote> [<remote> ...]   -> writes into dumps/
"""
import sys, os, time
import os as _os, sys as _sys; _d = _os.path.dirname(_os.path.abspath(__file__)); _sys.path[:0] = [p for p in (_os.path.normpath(_os.path.join(_d, '..', 'common')),   # shared helpers
                                  _os.path.normpath(_os.path.join(_d, '..', '..'))                                 ) if p not in _sys.path]  # repo root, for `pmca`
import senser_fix  # noqa: F401  -- fixes 0x8000 payload loss on PID 0x0336
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend

REMOTES = sys.argv[1:]
OUTDIR = os.environ.get("ZVE10_OUTDIR", "dumps")

def complete(dev):
    SenserPlatformBackend(dev).start()
    os.makedirs(OUTDIR, exist_ok=True)
    for r in REMOTES:
        local = os.path.join(OUTDIR, os.path.basename(r.rstrip("/")) or "root")
        print("pull %s -> %s" % (r, local), flush=True)
        try:
            with open(local, "wb") as f:
                dev.readFile(r, f)
            print("   ok, %d bytes" % os.path.getsize(local), flush=True)
        except Exception as e:
            print("   FAILED: %r" % (e,), flush=True)

if __name__ == "__main__":
    senserShellCommand(complete=complete)
