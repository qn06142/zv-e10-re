import sys, io, os, hashlib
sys.argv = ["s"]
import os as _os, sys as _sys; _d = _os.path.dirname(_os.path.abspath(__file__)); _sys.path[:0] = [p for p in (_os.path.normpath(_os.path.join(_d, '..', 'common')),   # shared helpers
                                  _os.path.normpath(_os.path.join(_d, '..', '..'))                                 ) if p not in _sys.path]  # repo root, for `pmca`
import senser_fix
import zve10_dumpall as m
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend

# (label, source, skip512, count512)
SAMPLES = [
    ("avcam_head",   "/system/av-cam.bin",   0,      128),   # 64KB
    ("avcam_1mb",    "/system/av-cam.bin",   2048,   128),
    ("avcam_8mb",    "/system/av-cam.bin",   16384,  128),
    ("avcam_tail",   "/system/av-cam.bin",   33640,  128),   # last full 64KB (file=17289388B)
    ("vmlinux_head", "/system/vmlinux.bin",  0,      128),   # control: known plaintext
    ("bonobo_head",  "/system/bonobo.bin",   0,      128),
    ("dfe_dat",      "/system/dfe_dat.bin",  0,      128),
    ("initrd_head",  "/system/initrd.img",   0,      128),
]

def complete(dev):
    SenserPlatformBackend(dev).start()
    raw = dev.dev
    dev.setTerminalEnable(False); dev.setTerminalEnable(True)
    m.pump(raw, 1.0, 6.0)
    os.makedirs("samples", exist_ok=True)
    for label, src, skip, cnt in SAMPLES:
        m.sh(raw, "dd if=%s of=/tmp/_s.bin bs=512 skip=%d count=%d 2>/dev/null; "
                  "echo S=$(busybox stat -c %%s /tmp/_s.bin)" % (src, skip, cnt),
             idle=1.0, hard=180.0, until=r"S=\d+")
        buf = io.BytesIO()
        try:
            dev.readFile("/tmp/_s.bin", buf)
        except Exception as e:
            print("%-14s pull err %r" % (label, e), flush=True)
        d = buf.getvalue()
        if d:
            open(os.path.join("samples", label + ".bin"), "wb").write(d)
        print("%-14s %6d bytes  md5=%s" % (label, len(d), hashlib.md5(d).hexdigest()[:12]), flush=True)
    m.sh(raw, "rm -f /tmp/_s.bin", idle=0.5, hard=30.0)
    dev.setTerminalEnable(False)

if __name__ == "__main__":
    m._preflight()
    senserShellCommand(complete=complete)
