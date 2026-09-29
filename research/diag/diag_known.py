import sys, io, hashlib
sys.argv = ["diag5"]
import os as _os, sys as _sys; _d = _os.path.dirname(_os.path.abspath(__file__)); _sys.path[:0] = [p for p in (_os.path.normpath(_os.path.join(_d, '..', 'common')),   # shared helpers
                                  _os.path.normpath(_os.path.join(_d, '..', '..'))                                 ) if p not in _sys.path]  # repo root, for `pmca`
import zve10_dumpall as m
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend

def complete(dev):
    SenserPlatformBackend(dev).start()
    raw = dev.dev
    dev.setTerminalEnable(False); dev.setTerminalEnable(True)
    m.pump(raw, 1.0, 6.0)

    # write a file with KNOWN, position-encoded content: 4096 lines of "AAAA000123\n"
    m.sh(raw, "rm -f /tmp/_k.bin; i=0; while [ $i -lt 4096 ]; do "
              "busybox printf 'LINE%06d____________________________________________________\\n' $i; "
              "i=$((i+1)); done > /tmp/_k.bin; echo D0NE", hard=180.0)
    r = m.sh(raw, "busybox ls -la /tmp/_k.bin; busybox md5sum /tmp/_k.bin", hard=60.0)
    print("staged:", [l.strip() for l in r.split("\n") if "_k.bin" in l], flush=True)

    buf = io.BytesIO()
    try:
        dev.readFile("/tmp/_k.bin", buf)
        print("pull clean", flush=True)
    except Exception as e:
        print("pull raised:", repr(e), flush=True)
    d = buf.getvalue()
    print("pulled %d bytes" % len(d), flush=True)
    print("  head: %r" % d[:60], flush=True)
    print("  tail: %r" % d[-60:], flush=True)
    print("  host md5: %s" % hashlib.md5(d).hexdigest(), flush=True)
    m.sh(raw, "rm -f /tmp/_k.bin", hard=20.0)
    dev.setTerminalEnable(False)

senserShellCommand(complete=complete)
