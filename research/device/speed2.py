import sys, io, time
sys.argv = ["t"]
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
    for tgt, N in (("/log/_d.bin", 2*1024*1024), ("/log/_d.bin", 8*1024*1024)):
        t0 = time.time()
        r = m.sh(raw, "dd if=/dev/nflasha7 of=%s bs=512 skip=0 count=%d 2>/dev/null; "
                      "echo S=$(busybox stat -c %%s %s)" % (tgt, N//512, tgt),
                 idle=1.0, hard=600.0, until=r"S=\d+")
        t1 = time.time()
        import re
        mm = re.search(r"S=(\d+)", r)
        print("dd %8d -> %s in %5.1fs (%.2f MB/s) staged=%s"
              % (N, tgt, t1-t0, N/1e6/max(t1-t0,.1), mm.group(1) if mm else "?"), flush=True)
        if not mm: break
        t2 = time.time()
        buf = io.BytesIO()
        try: dev.readFile(tgt, buf)
        except Exception as e: print("   pull err", repr(e), flush=True)
        t3 = time.time()
        print("   pull %d bytes in %5.1fs (%.2f MB/s)" % (len(buf.getvalue()), t3-t2, len(buf.getvalue())/1e6/max(t3-t2,.1)), flush=True)
    m.sh(raw, "rm -f /log/_d.bin", idle=0.5, hard=30.0)
    dev.setTerminalEnable(False)

if __name__ == "__main__":
    m._preflight()
    senserShellCommand(complete=complete)
