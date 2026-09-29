"""Dump the ZV-E10 firmware blobs from /system (files, not raw partitions).

Why files beat partitions: /system's contents are what actually matter --
av-cam.bin IS the liro RTOS image (ISP/AF/AE/AWB), vmlinux.bin is the kernel,
initrd.img is the rootfs. Together ~24MB instead of 1.4GB of mostly-empty NAND.

Transport: chunked dd -> staging file -> pmca readFile (bulk protocol), with a
per-chunk md5 verified against the camera's own busybox md5sum. Resumes from
the local file's current size, so an interrupted run just re-runs.

usage: zve10_dumpfw.py
"""
import sys, os, time, re, io, hashlib
import os as _os, sys as _sys; _d = _os.path.dirname(_os.path.abspath(__file__)); _sys.path[:0] = [p for p in (_os.path.normpath(_os.path.join(_d, '..', 'common')),   # shared helpers
                                  _os.path.normpath(_os.path.join(_d, '..', '..'))                                 ) if p not in _sys.path]  # repo root, for `pmca`
import senser_fix  # noqa: F401  -- fixes 0x8000 payload loss on PID 0x0336
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend
from zve10_dumpall import pump, sh, _preflight

OUTDIR = os.environ.get("ZVE10_OUTDIR", "fw")
CHUNK  = int(os.environ.get("ZVE10_CHUNK", 4 * 1024 * 1024))
STAGE  = "/log/_f.bin"

# (local name, remote path, size) -- sizes from `ls -la /system`
FILES = [
    ("dfe_dat.bin",   "/system/dfe_dat.bin",       65536),
    ("dfe_app.bin",   "/system/dfe_app.bin",        1956),
    ("ldr_drv.bin",   "/system/ldr_drv.bin",        7012),
    ("lif_app.bin",   "/system/lif_app.bin",        6716),
    ("wole_app.bin",  "/system/wole_app.bin",      10848),
    ("bt_firm.hcd",   "/system/bt_firm.hcd",       61787),
    ("bonobo.bin",    "/system/bonobo.bin",       172144),
    ("initrd.img",    "/system/initrd.img",      2183168),
    ("vmlinux.bin",   "/system/vmlinux.bin",     4117760),
    ("av-cam.bin",    "/system/av-cam.bin",     17289388),   # the ISP firmware
]

def dump(dev, raw, name, remote, size):
    local = os.path.join(OUTDIR, name)
    done = os.path.getsize(local) if os.path.exists(local) else 0
    if done >= size:
        print("[skip] %-14s complete (%d B)" % (name, done), flush=True)
        return True
    print("[dump] %-14s %9d B  (resume at %d)" % (name, size, done), flush=True)
    with open(local, "ab") as f:
        while done < size:
            n = min(CHUNK, size - done)
            t0 = time.time()
            # one round-trip: dd the slice, then report its size+md5
            r = sh(raw, "dd if=%s of=%s bs=512 skip=%d count=%d 2>/dev/null; "
                        "echo S=$(busybox stat -c %%s %s) M=$(busybox md5sum %s | busybox cut -d' ' -f1)"
                        % (remote, STAGE, done // 512, (n + 511) // 512, STAGE, STAGE),
                   idle=1.0, hard=600.0, until=r"S=\d+\s+M=[0-9a-f]{32}")
            mi = re.search(r"S=(\d+)\s+M=([0-9a-f]{32})", r)
            if not mi:
                print("   ! no marker, stopping", flush=True); return False
            cam_size, cam_md5 = int(mi.group(1)), mi.group(2)
            buf = io.BytesIO()
            try:
                dev.readFile(STAGE, buf)
            except Exception as e:
                print("   ! pull failed at %d: %r" % (done, e), flush=True); return False
            data = buf.getvalue()
            if len(data) < cam_size:
                print("   ! short pull %d < %d, stopping" % (len(data), cam_size), flush=True); return False
            if hashlib.md5(data[:cam_size]).hexdigest() != cam_md5:
                print("   ! MD5 MISMATCH at %d, stopping" % done, flush=True); return False
            f.write(data[:n]); f.flush()
            done += n
            dt = time.time() - t0
            print("   %9d / %9d  (%5.1f%%)  %.2f MB/s" % (done, size, 100.0 * done / size,
                                                          n / 1e6 / max(dt, .01)), flush=True)
    print("   -> %s  %d B" % (local, os.path.getsize(local)), flush=True)
    return True

def complete(dev):
    SenserPlatformBackend(dev).start()
    raw = dev.dev
    dev.setTerminalEnable(False); dev.setTerminalEnable(True)
    pump(raw, 1.0, 6.0)
    os.makedirs(OUTDIR, exist_ok=True)
    try:
        for name, remote, size in FILES:
            if not dump(dev, raw, name, remote, size):
                break          # session degraded -- next run resumes
    finally:
        try: sh(raw, "rm -f %s" % STAGE, idle=0.5, hard=20.0)
        except Exception: pass
        dev.setTerminalEnable(False)

if __name__ == "__main__":
    _preflight()
    senserShellCommand(complete=complete)
