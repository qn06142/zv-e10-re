import sys, io, hashlib
sys.argv = ["diag3"]
import os as _os, sys as _sys; _d = _os.path.dirname(_os.path.abspath(__file__)); _sys.path[:0] = [p for p in (_os.path.normpath(_os.path.join(_d, '..', 'common')),   # shared helpers
                                  _os.path.normpath(_os.path.join(_d, '..', '..'))                                 ) if p not in _sys.path]  # repo root, for `pmca`
import zve10_dumpall as m
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend

WANT = 262144
PAD  = 32768

def complete(dev):
    SenserPlatformBackend(dev).start()
    raw = dev.dev
    dev.setTerminalEnable(False); dev.setTerminalEnable(True)
    m.pump(raw, 1.0, 6.0)

    m.sh(raw, "rm -f /tmp/_d.bin; dd if=/dev/nflasha13 of=/tmp/_d.bin bs=512 skip=0 count=%d 2>/dev/null; echo D0NE"
              % ((WANT + PAD) // 512), hard=120.0)
    buf = io.BytesIO()
    try:
        dev.readFile("/tmp/_d.bin", buf)
        print("pull returned cleanly", flush=True)
    except Exception as e:
        print("pull raised (expected):", repr(e), flush=True)
    data = buf.getvalue()
    print("got %d, want %d -> %s" % (len(data), WANT, "ENOUGH" if len(data) >= WANT else "SHORT"), flush=True)

    if len(data) >= WANT:
        print("host md5 of first %d: %s" % (WANT, hashlib.md5(data[:WANT]).hexdigest()), flush=True)
        m.sh(raw, "rm -f /tmp/_p.bin; dd if=/dev/nflasha13 of=/tmp/_p.bin bs=512 skip=0 count=%d 2>/dev/null; echo D0NE"
                  % (WANT // 512), hard=120.0)
        r2 = m.sh(raw, "busybox md5sum /tmp/_p.bin", hard=60.0)
        print("camera md5:", [l for l in r2.split("\n") if len(l.strip()) > 30][-1:], flush=True)
        m.sh(raw, "rm -f /tmp/_p.bin", hard=20.0)
    m.sh(raw, "rm -f /tmp/_d.bin", hard=20.0)
    dev.setTerminalEnable(False)

senserShellCommand(complete=complete)
