import sys, io, time, hashlib
sys.argv = ["speed"]
import os as _os, sys as _sys; _d = _os.path.dirname(_os.path.abspath(__file__)); _sys.path[:0] = [p for p in (_os.path.normpath(_os.path.join(_d, '..', 'common')),   # shared helpers
                                  _os.path.normpath(_os.path.join(_d, '..', '..'))                                 ) if p not in _sys.path]  # repo root, for `pmca`
import senser_fix
import zve10_dumpall as m
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend

def complete(dev):
    SenserPlatformBackend(dev).start()
    raw = dev.dev
    dev.setTerminalEnable(False); dev.setTerminalEnable(True)
    m.pump(raw, 1.0, 6.0)

    for N in (1048576, 4194304, 8388608):
        t0 = time.time()
        m.sh(raw, "rm -f /tmp/_d.bin; dd if=/dev/nflasha7 of=/tmp/_d.bin bs=512 skip=0 count=%d 2>/dev/null; echo D0NE"
                  % (N // 512), hard=300.0)
        t1 = time.time()
        buf = io.BytesIO()
        err = ""
        try:
            dev.readFile("/tmp/_d.bin", buf)
        except Exception as e:
            err = repr(e)
        t2 = time.time()
        got = len(buf.getvalue())
        print("N=%8d  dd=%5.1fs  pull=%5.1fs  got=%8d  %6.0f KB/s  %s"
              % (N, t1-t0, t2-t1, got, got/1024.0/max(t2-t1, .001), err), flush=True)
        if got != N:
            print("   (short/failed -- stopping ladder)", flush=True); break
    m.sh(raw, "rm -f /tmp/_d.bin", hard=30.0)
    dev.setTerminalEnable(False)

if __name__ == "__main__":
    senserShellCommand(complete=complete)
