"""Dump ZV-E10 firmware blobs onto the FAT32 SD card (fast path).

The card is mounted by the camera's Linux at /tmp/sd (vfat). We dd each
firmware file from /system into /tmp/sd/fw_dump/<name> and verify by md5sum
on BOTH the source and the card copy. No pmca bulk transfer -> ~1.6MB/s local
dd only. ~24MB total, well under the card's free space.

Safety:
  - writes ONLY into /tmp/sd/fw_dump/ (never /system, never PRIVATE)
  - read-only on the camera's firmware (dd if=..., of=... onto the card)
  - never formats or touches the card's existing folders
"""
import sys, os, time, re
import os as _os, sys as _sys; _d = _os.path.dirname(_os.path.abspath(__file__)); _sys.path[:0] = [p for p in (_os.path.normpath(_os.path.join(_d, '..', 'common')),   # shared helpers
                                  _os.path.normpath(_os.path.join(_d, '..', '..'))                                 ) if p not in _sys.path]  # repo root, for `pmca`
import senser_fix  # noqa: F401
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend
from zve10_dumpall import pump, sh, _preflight

# (name, remote path) -- sizes from earlier ls -la /system
FILES = [
    ("dfe_dat.bin",   "/system/dfe_dat.bin"),
    ("dfe_app.bin",   "/system/dfe_app.bin"),
    ("ldr_drv.bin",   "/system/ldr_drv.bin"),
    ("lif_app.bin",   "/system/lif_app.bin"),
    ("wole_app.bin",  "/system/wole_app.bin"),
    ("bt_firm.hcd",   "/system/bt_firm.hcd"),
    ("bonobo.bin",    "/system/bonobo.bin"),
    ("initrd.img",    "/system/initrd.img"),
    ("vmlinux.bin",   "/system/vmlinux.bin"),
    ("av-cam.bin",    "/system/av-cam.bin"),
]
MOUNT, SUB = "/tmp/sd", "fw_dump"

def dump(dev, raw, name, remote):
    dst = "%s/%s/%s" % (MOUNT, SUB, name)
    print("[dump] %-14s -> card" % name, flush=True)
    # dd + compare md5 of source vs card copy in ONE round-trip
    r = sh(raw,
        "dd if=%s of=%s bs=512 2>/dev/null; "
        "S=$(busybox md5sum %s | busybox cut -d' ' -f1); "
        "D=$(busybox md5sum %s | busybox cut -d' ' -f1); "
        "echo CMP S=$S D=$D"
        % (remote, dst, remote, dst),
        idle=1.0, hard=600.0, until=r"CMP S=[0-9a-f]{32} D=[0-9a-f]{32}")
    m = re.search(r"CMP S=([0-9a-f]{32}) D=([0-9a-f]{32})", r)
    if not m:
        print("   ! no CMP marker", flush=True); return False
    ok = m.group(1) == m.group(2)
    print("   %s  S=%s" % ("OK " if ok else "BAD", m.group(1)), flush=True)
    return ok

def complete(dev):
    SenserPlatformBackend(dev).start()
    raw = dev.dev
    dev.setTerminalEnable(False); dev.setTerminalEnable(True)
    pump(raw, 1.0, 6.0)
    # mount the FAT32 card (idempotent: it may already be mounted from a
    # prior shell session -- re-mounting a mounted device fails with EBUSY)
    sh(raw, "busybox mkdir -p %s/%s" % (MOUNT, SUB), idle=0.5, hard=20.0)
    mr = sh(raw,
        "busybox mount | busybox grep -q '%s' || busybox mount -t vfat /dev/mmca1 %s; echo MRC=$?"
        % (MOUNT, MOUNT), idle=1.0, hard=30.0)
    if "MRC=0" not in mr:
        print("!! card not mounted, aborting: %r" % mr[-80:], flush=True)
        dev.setTerminalEnable(False); return
    ok_all = True
    try:
        for name, remote in FILES:
            if not dump(dev, raw, name, remote):
                ok_all = False; break
    finally:
        sh(raw, "busybox sync", idle=1.0, hard=30.0)
        sh(raw, "busybox umount %s; echo URC=$?" % MOUNT, idle=1.0, hard=30.0)
        dev.setTerminalEnable(False)
    print("ALL OK" if ok_all else "INCOMPLETE", flush=True)

if __name__ == "__main__":
    _preflight()
    senserShellCommand(complete=complete)
