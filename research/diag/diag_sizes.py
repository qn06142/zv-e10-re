import sys, io
sys.argv = ["diag2"]
import os as _os, sys as _sys; _d = _os.path.dirname(_os.path.abspath(__file__)); _sys.path[:0] = [p for p in (_os.path.normpath(_os.path.join(_d, '..', 'common')),   # shared helpers
                                  _os.path.normpath(_os.path.join(_d, '..', '..'))                                 ) if p not in _sys.path]  # repo root, for `pmca`
import zve10_dumpall as m
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend

SIZES = [262144, 131072, 65536]   # 256K, 128K, 64K

def complete(dev):
    SenserPlatformBackend(dev).start()
    raw = dev.dev
    dev.setTerminalEnable(False); dev.setTerminalEnable(True)
    m.pump(raw, 1.0, 6.0)
    for size in SIZES:
        m.sh(raw, "rm -f /tmp/_d.bin; dd if=/dev/nflasha13 of=/tmp/_d.bin bs=512 skip=0 count=%d 2>/dev/null; echo D0NE"
                  % (size // 512), hard=90.0)
        buf = io.BytesIO()
        try:
            dev.readFile("/tmp/_d.bin", buf)
            got = len(buf.getvalue())
            print("size %7d -> pulled %7d  %s" % (size, got, "OK" if got == size else "SHORT"), flush=True)
        except Exception as e:
            print("size %7d -> FAILED after %d (%r)" % (size, len(buf.getvalue()), e), flush=True)
    m.sh(raw, "rm -f /tmp/_d.bin", hard=20.0)
    dev.setTerminalEnable(False)

senserShellCommand(complete=complete)
