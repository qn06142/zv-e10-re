import sys, io, hashlib
sys.argv = ["diag4"]
import os as _os, sys as _sys; _d = _os.path.dirname(_os.path.abspath(__file__)); _sys.path[:0] = [p for p in (_os.path.normpath(_os.path.join(_d, '..', 'common')),   # shared helpers
                                  _os.path.normpath(_os.path.join(_d, '..', '..'))                                 ) if p not in _sys.path]  # repo root, for `pmca`
import zve10_dumpall as m
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend

WANT = 262144
PAD  = 32768

def cam_md5(raw, dev, skip512, count512, tag):
    m.sh(raw, "rm -f /tmp/_p.bin; dd if=/dev/nflasha13 of=/tmp/_p.bin bs=512 skip=%d count=%d 2>/dev/null; echo D0NE"
              % (skip512, count512), hard=120.0)
    r = m.sh(raw, "busybox md5sum /tmp/_p.bin", hard=60.0)
    h = [l.strip().split()[0] for l in r.split("\n") if len(l.strip()) > 32 and " " in l.strip()]
    print("  camera md5 %-22s = %s" % (tag, h[-1] if h else "?"), flush=True)
    m.sh(raw, "rm -f /tmp/_p.bin", hard=20.0)

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
    except Exception:
        pass
    data = buf.getvalue()
    print("pulled %d bytes from a %d-byte staged file" % (len(data), WANT + PAD), flush=True)
    print("  host md5 of pulled     = %s" % hashlib.md5(data).hexdigest(), flush=True)
    m.sh(raw, "rm -f /tmp/_d.bin", hard=20.0)

    # which range of the partition does the pulled data actually equal?
    cam_md5(raw, dev, 0,  len(data) // 512, "bytes [0:%d]" % len(data))
    cam_md5(raw, dev, PAD // 512, len(data) // 512, "bytes [%d:%d]" % (PAD, PAD + len(data)))
    dev.setTerminalEnable(False)

senserShellCommand(complete=complete)
