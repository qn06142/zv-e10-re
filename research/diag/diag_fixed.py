import sys, io, hashlib
sys.argv = ["diag7"]
import os as _os, sys as _sys; _d = _os.path.dirname(_os.path.abspath(__file__)); _sys.path[:0] = [p for p in (_os.path.normpath(_os.path.join(_d, '..', 'common')),   # shared helpers
                                  _os.path.normpath(_os.path.join(_d, '..', '..'))                                 ) if p not in _sys.path]  # repo root, for `pmca`
import senser_fix                      # monkeypatch BEFORE use
import zve10_dumpall as m
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend

def complete(dev):
    SenserPlatformBackend(dev).start()
    raw = dev.dev
    dev.setTerminalEnable(False); dev.setTerminalEnable(True)
    m.pump(raw, 1.0, 6.0)

    N = 262144
    m.sh(raw, "rm -f /tmp/_d.bin; dd if=/dev/nflasha13 of=/tmp/_d.bin bs=512 skip=0 count=%d 2>/dev/null; echo D0NE"
              % (N // 512), hard=120.0)
    r = m.sh(raw, "busybox md5sum /tmp/_d.bin", hard=60.0)
    cam = [l.strip().split()[0] for l in r.split("\n") if len(l.strip()) > 32 and "  " in l]
    cam = cam[-1] if cam else "?"

    buf = io.BytesIO()
    try:
        dev.readFile("/tmp/_d.bin", buf)
        print("pull returned CLEANLY", flush=True)
    except Exception as e:
        print("pull raised:", repr(e), flush=True)
    d = buf.getvalue()
    host = hashlib.md5(d).hexdigest()
    print("staged %d | pulled %d" % (N, len(d)), flush=True)
    print("camera md5 %s" % cam, flush=True)
    print("host   md5 %s" % host, flush=True)
    print("MATCH: %s" % (cam == host and len(d) == N), flush=True)
    m.sh(raw, "rm -f /tmp/_d.bin", hard=20.0)
    dev.setTerminalEnable(False)

senserShellCommand(complete=complete)
