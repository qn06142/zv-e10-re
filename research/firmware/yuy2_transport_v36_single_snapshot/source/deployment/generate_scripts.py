import hashlib
from pathlib import Path

pkg = Path(r"C:\Users\qn061\Documents\Codex\2026-10-22\chec\outputs\vga-v36\flash-package")
work_deploy = Path(r"C:\Users\qn061\Documents\Codex\2026-10-22\chec\work\vga-v36\deployment")

preflight_sh = """#!/bin/sh
set -eu
BB=/bin/busybox
hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
guard() { [ "$(hash "$1")" = "$2" ] || { echo "HASH_GUARD_FAILED:$1"; exit 1; }; }
P=$($BB pidof im.elf)
case "$P" in ''|*[!0-9]*) echo PROCESS_GUARD_FAILED; exit 1;; esac
if $BB grep -E 'libInfraStreamingUsb|yuy2_640|yc_observer|yc_probe' /proc/$P/maps; then echo COLD_BOOT_REQUIRED; exit 1; fi
if $BB grep -E ' /usr/(lib/libInfraStreamingUsb.so|lib/libInfraUsbCmn.so|lib/libBizFw.so|.local/kmod/usbg_video.ko) ' /proc/mounts; then echo OVERLAY_GUARD_FAILED; exit 1; fi
guard /usr/lib/libInfraStreamingUsb.so c16af3a036529b89d23fa4ccfd059ec3
guard /usr/lib/yuy2_640_v35vga.so e6b9fa6947a21e5a6a1603e070a1d00f
guard /usr/lib/yuy2_640_v33vga.so 87ddc16bd8e0774926e5eb6d16165d20
guard /usr/lib/yuy2_640_v29full.so b4c6012cd876210fcfd0cf4b0d6f67e0
guard /usr/share/yuy2-recovery-v35vga/libInfraStreamingUsb.previous.so ca3cbbc5947caf3373ebe451343fb926
guard /usr/share/yuy2-recovery-v29full/libInfraStreamingUsb.v24p.so 5fde77e394572ebcf420f8941575f6c4
guard /usr/lib/yuy2_640_v24p.so 9181ef744955190d04728cf4ef7965c5
guard /usr/kmod/dmm.ko 15c8f7807b291c0af3c77fe55848577f
guard /usr/kmod/usbg_video.ko c1cad400372e26eca729e4b9bc47a237
guard /usr/lib/libInfraUsbCmn.so 31308976206a837f6f5c571992d2b499
guard /usr/lib/libObj.so 0b4be3fb599b539c69c782bd400dd8e9
guard /lib/libpthread.so.0 09cb541e6e785dd6bfeb76d74f29f5d2
guard /usr/lib/libBizFw.so 6416a5a6780bbe829eb30d85fc8e8dad
guard /system/av-cam.bin 90096db2c76148f4f9db5d104e5c608c
guard /setting/DmmConfig.bin 9f197ff9b300e49ab531b6f9e794253e
[ -x /usr/share/yuy2-recovery-v35vga/rollback.sh ]
[ ! -e /usr/lib/yuy2_640_v36vga.so ]
[ ! -e /usr/share/yuy2-recovery-v36vga ]
[ ! -e /usr/lib/.yuy2_v36vga.new ]
[ ! -e /usr/lib/.libInfraStreamingUsb.v36vga.new ]
SPACE=${1:-/log/yuy2_640_v36vga/space-check.elf}
guard "$SPACE" c2c8b809405bf52e3a7fa8df88aa95eb
$BB chmod 755 "$SPACE"
"$SPACE"
$BB cat /proc/uptime
$BB md5sum /usr/lib/libInfraStreamingUsb.so /usr/lib/yuy2_640_v35vga.so /usr/lib/yuy2_640_v24p.so /usr/kmod/usbg_video.ko /usr/lib/libBizFw.so /usr/lib/libInfraUsbCmn.so /system/av-cam.bin /setting/DmmConfig.bin
$BB cat /proc/udm/dmm_units
echo DMM_LISTING_IS_NOT_PROOF_OF_ACTIVE_STREAM_SOURCE
echo V36_PREFLIGHT_OK
""".replace("\r\n", "\n")

rollback_sh = """#!/bin/sh
set -eu
BB=/bin/busybox
B=/usr/share/yuy2-recovery-v36vga
hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
[ "$(hash "$B/libInfraStreamingUsb.previous.so")" = c16af3a036529b89d23fa4ccfd059ec3 ]
[ "$(hash /usr/lib/yuy2_640_v35vga.so)" = e6b9fa6947a21e5a6a1603e070a1d00f ]
P=$($BB pidof im.elf)
case "$P" in ''|*[!0-9]*) exit 1;; esac
if $BB grep -E 'libInfraStreamingUsb|yuy2_640|yc_observer|yc_probe' /proc/$P/maps; then echo COLD_BOOT_BEFORE_ROLLBACK; exit 1; fi
case "$(hash /usr/lib/libInfraStreamingUsb.so)" in 886445056d2eba99ef62df3a9def5e0f|c16af3a036529b89d23fa4ccfd059ec3) ;; *) echo UNKNOWN_STREAM_REFUSED; exit 1;; esac
$BB mount -o remount,rw /usr
trap '$BB sync; $BB mount -o remount,ro /usr' 0
$BB cp "$B/libInfraStreamingUsb.previous.so" /usr/lib/.libInfraStreamingUsb.v36vga.restore
$BB chmod 755 /usr/lib/.libInfraStreamingUsb.v36vga.restore
[ "$(hash /usr/lib/.libInfraStreamingUsb.v36vga.restore)" = c16af3a036529b89d23fa4ccfd059ec3 ]
$BB mv /usr/lib/.libInfraStreamingUsb.v36vga.restore /usr/lib/libInfraStreamingUsb.so
[ "$(hash /usr/lib/libInfraStreamingUsb.so)" = c16af3a036529b89d23fa4ccfd059ec3 ]
$BB sync
echo V36_ROLLED_BACK_TO_PREVIOUS_V35_REBOOT_REQUIRED
""".replace("\r\n", "\n")

rollback_md5 = hashlib.md5(rollback_sh.encode("ascii")).hexdigest()

install_sh = f"""#!/bin/sh
set -eu
BB=/bin/busybox
D=/log/yuy2_640_v36vga
B=/usr/share/yuy2-recovery-v36vga
hash() {{ $BB md5sum "$1" | $BB cut -d ' ' -f 1; }}
$BB sh "$D/preflight.sh"
[ "$(hash "$D/libInfraStreamingUsb.persistent.so")" = 886445056d2eba99ef62df3a9def5e0f ]
[ "$(hash "$D/yuy2_640_v36vga.so")" = c2e06b5a7a9f1361c4fb2a087d5e8fe2 ]
[ "$(hash "$D/rollback.sh")" = {rollback_md5} ]
$BB sh -n "$D/rollback.sh"
BACKED=0
DONE=0
RW=0
on_exit() {{
 RC=$?
 trap - 0
 set +e
 if [ "$DONE" != 1 ] && [ "$BACKED" = 1 ]; then
  echo V36_INSTALL_FAILED_RESTORING_PREVIOUS
  $BB cp "$B/libInfraStreamingUsb.previous.so" /usr/lib/.libInfraStreamingUsb.v36vga.restore
  $BB chmod 755 /usr/lib/.libInfraStreamingUsb.v36vga.restore
  if [ "$(hash /usr/lib/.libInfraStreamingUsb.v36vga.restore)" = c16af3a036529b89d23fa4ccfd059ec3 ]; then
   $BB mv /usr/lib/.libInfraStreamingUsb.v36vga.restore /usr/lib/libInfraStreamingUsb.so
  fi
  if [ "$(hash /usr/lib/libInfraStreamingUsb.so)" = c16af3a036529b89d23fa4ccfd059ec3 ]; then echo V36_FAILURE_RESTORED_PREVIOUS; else echo V36_RECOVERY_REQUIRED; fi
 fi
 $BB sync
 if [ "$RW" = 1 ]; then $BB mount -o remount,ro /usr || {{ echo V36_REMOUNT_RO_FAILED; RC=1; }}; fi
 exit "$RC"
}}
trap on_exit 0
trap 'exit 1' 1 2 15
$BB mount -o remount,rw /usr
RW=1
$BB mkdir "$B"
$BB cp /usr/lib/libInfraStreamingUsb.so "$B/libInfraStreamingUsb.previous.so"
[ "$(hash "$B/libInfraStreamingUsb.previous.so")" = c16af3a036529b89d23fa4ccfd059ec3 ]
BACKED=1
$BB cp /usr/share/yuy2-recovery-v29full/libInfraStreamingUsb.v24p.so "$B/libInfraStreamingUsb.v24p.so"
[ "$(hash "$B/libInfraStreamingUsb.v24p.so")" = 5fde77e394572ebcf420f8941575f6c4 ]
$BB ln /usr/lib/libInfraStreamingUsb.so "$B/libInfraStreamingUsb.previous-inode.so"
$BB cp "$D/rollback.sh" "$B/rollback.sh"
$BB chmod 755 "$B/rollback.sh"
[ "$(hash "$B/rollback.sh")" = {rollback_md5} ]
$BB sync
$BB cp "$D/yuy2_640_v36vga.so" /usr/lib/.yuy2_v36vga.new
$BB chmod 755 /usr/lib/.yuy2_v36vga.new
[ "$(hash /usr/lib/.yuy2_v36vga.new)" = c2e06b5a7a9f1361c4fb2a087d5e8fe2 ]
$BB mv /usr/lib/.yuy2_v36vga.new /usr/lib/yuy2_640_v36vga.so
$BB cp "$D/libInfraStreamingUsb.persistent.so" /usr/lib/.libInfraStreamingUsb.v36vga.new
$BB chmod 755 /usr/lib/.libInfraStreamingUsb.v36vga.new
[ "$(hash /usr/lib/.libInfraStreamingUsb.v36vga.new)" = 886445056d2eba99ef62df3a9def5e0f ]
# Dependency exists and is verified before the streaming pathname is activated.
$BB sync
$BB mv /usr/lib/.libInfraStreamingUsb.v36vga.new /usr/lib/libInfraStreamingUsb.so
[ "$(hash /usr/lib/libInfraStreamingUsb.so)" = 886445056d2eba99ef62df3a9def5e0f ]
[ "$(hash /usr/lib/yuy2_640_v36vga.so)" = c2e06b5a7a9f1361c4fb2a087d5e8fe2 ]
[ "$(hash /usr/lib/yuy2_640_v35vga.so)" = e6b9fa6947a21e5a6a1603e070a1d00f ]
[ "$(hash /usr/lib/yuy2_640_v24p.so)" = 9181ef744955190d04728cf4ef7965c5 ]
[ "$(hash /usr/kmod/usbg_video.ko)" = c1cad400372e26eca729e4b9bc47a237 ]
[ "$(hash /usr/lib/libBizFw.so)" = 6416a5a6780bbe829eb30d85fc8e8dad ]
[ "$(hash /usr/lib/libInfraUsbCmn.so)" = 31308976206a837f6f5c571992d2b499 ]
[ "$(hash /system/av-cam.bin)" = 90096db2c76148f4f9db5d104e5c608c ]
[ "$(hash /setting/DmmConfig.bin)" = 9f197ff9b300e49ab531b6f9e794253e ]
$BB md5sum /usr/lib/libInfraStreamingUsb.so /usr/lib/yuy2_640_v36vga.so /usr/lib/yuy2_640_v35vga.so /usr/lib/yuy2_640_v24p.so /usr/kmod/usbg_video.ko > "$D/installed.md5"
$BB sync
$BB mount -o remount,ro /usr
RW=0
DONE=1
echo V36_FILES_VERIFIED_REBOOT_REQUIRED
""".replace("\r\n", "\n")

for target_dir in [pkg, work_deploy]:
    (target_dir / "preflight.sh").write_bytes(preflight_sh.encode("ascii"))
    (target_dir / "rollback.sh").write_bytes(rollback_sh.encode("ascii"))
    (target_dir / "install.sh").write_bytes(install_sh.encode("ascii"))

print("Wrote scripts successfully.")
print("Rollback MD5:", rollback_md5)
print("Install MD5:", hashlib.md5(install_sh.encode("ascii")).hexdigest())
print("Preflight MD5:", hashlib.md5(preflight_sh.encode("ascii")).hexdigest())
