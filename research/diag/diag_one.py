import sys, os, io, time
sys.argv = ["diag"]
import os as _os, sys as _sys; _d = _os.path.dirname(_os.path.abspath(__file__)); _sys.path[:0] = [p for p in (_os.path.normpath(_os.path.join(_d, '..', 'common')),   # shared helpers
                                  _os.path.normpath(_os.path.join(_d, '..', '..'))                                 ) if p not in _sys.path]  # repo root, for `pmca`
import zve10_dumpall as m
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend

def complete(dev):
    SenserPlatformBackend(dev).start()
    raw = dev.dev
    dev.setTerminalEnable(False); dev.setTerminalEnable(True)
    print("banner:", repr(m.pump(raw, 1.0, 6.0)[-120:]), flush=True)

    cmd = ("rm -f /tmp/_d.bin; dd if=/dev/nflasha13 of=/tmp/_d.bin bs=512 skip=0 count=1024 2>&1; echo D0NE")
    r = m.sh(raw, cmd, hard=90.0)
    print("DD REPLY:", repr(r[-300:]), flush=True)

    r2 = m.sh(raw, "busybox ls -la /tmp/_d.bin; busybox md5sum /tmp/_d.bin", hard=60.0)
    print("STAGE:", repr(r2[-300:]), flush=True)

    buf = io.BytesIO()
    try:
        dev.readFile("/tmp/_d.bin", buf)
        print("PULL OK:", len(buf.getvalue()), "bytes", flush=True)
        open("dumps/_diag.bin", "wb").write(buf.getvalue())
    except Exception as e:
        print("PULL FAILED after", len(buf.getvalue()), "bytes:", repr(e), flush=True)
        if buf.getvalue():
            open("dumps/_diag.bin", "wb").write(buf.getvalue())
    m.sh(raw, "rm -f /tmp/_d.bin", hard=20.0)
    dev.setTerminalEnable(False)

senserShellCommand(complete=complete)
