import sys, io, hashlib
sys.argv = ["diag6"]
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

    # Known content, built by doubling a seed file -> 256KB, no shell loops.
    m.sh(raw, "rm -f /tmp/_k.bin /tmp/_s.bin; "
              "busybox dd if=/dev/urandom of=/tmp/_s.bin bs=1024 count=4 2>/dev/null; "
              "cp /tmp/_s.bin /tmp/_k.bin; echo D0NE", hard=90.0)
    for _ in range(6):   # 4K -> 256K
        m.sh(raw, "cat /tmp/_k.bin /tmp/_k.bin > /tmp/_t.bin; mv /tmp/_t.bin /tmp/_k.bin; echo D0NE", hard=90.0)
    r = m.sh(raw, "busybox ls -la /tmp/_k.bin; busybox md5sum /tmp/_k.bin", hard=60.0)
    info = [l.strip() for l in r.split("\n") if "_k.bin" in l and ("rw-" in l or len(l.strip()) > 32)]
    print("staged:", info, flush=True)

    buf = io.BytesIO()
    try:
        dev.readFile("/tmp/_k.bin", buf)
        print("pull clean", flush=True)
    except Exception as e:
        print("pull raised:", repr(e), flush=True)
    d = buf.getvalue()
    print("pulled %d bytes, host md5 %s" % (len(d), hashlib.md5(d).hexdigest()), flush=True)
    # the file is a repeating 4096-byte block: check WHICH block boundary we start at
    if d:
        seed = d[:4096]
        okrep = all(d[i:i+4096] == seed for i in range(0, (len(d)//4096)*4096, 4096))
        print("  pulled data is uniform 4K-repeating: %s" % okrep, flush=True)
    m.sh(raw, "rm -f /tmp/_k.bin /tmp/_s.bin", hard=20.0)
    dev.setTerminalEnable(False)

senserShellCommand(complete=complete)
