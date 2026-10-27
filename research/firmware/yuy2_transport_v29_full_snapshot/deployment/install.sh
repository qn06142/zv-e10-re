#!/bin/sh
set -eu
BB=/bin/busybox
D=/log/yuy2_640_v29full
B=/usr/share/yuy2-recovery-v29full
hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
$BB sh "$D/preflight.sh"
[ "$(hash "$D/libInfraStreamingUsb.persistent.so")" = 32a2d064d25720c17dd9a43927d4a835 ]
[ "$(hash "$D/yuy2_640_v29full.so")" = b4c6012cd876210fcfd0cf4b0d6f67e0 ]
[ "$(hash "$D/rollback.sh")" = 3473352a715f06dc542a344729f80262 ]
$BB sh -n "$D/rollback.sh"
BACKED=0
DONE=0
RW=0
on_exit() {
 RC=$?
 trap - 0
 set +e
 if [ "$DONE" != 1 ] && [ "$BACKED" = 1 ]; then
  echo V29_INSTALL_FAILED_RESTORING_PREVIOUS
  $BB cp "$B/libInfraStreamingUsb.previous.so" /usr/lib/.libInfraStreamingUsb.v29full.restore
  $BB chmod 755 /usr/lib/.libInfraStreamingUsb.v29full.restore
  if [ "$(hash /usr/lib/.libInfraStreamingUsb.v29full.restore)" = 27f4f4696c724caa8348edc51c86a517 ]; then
   $BB mv /usr/lib/.libInfraStreamingUsb.v29full.restore /usr/lib/libInfraStreamingUsb.so
  fi
  if [ "$(hash /usr/lib/libInfraStreamingUsb.so)" = 27f4f4696c724caa8348edc51c86a517 ]; then echo V29_FAILURE_RESTORED_PREVIOUS; else echo V29_RECOVERY_REQUIRED; fi
 fi
 $BB sync
 if [ "$RW" = 1 ]; then $BB mount -o remount,ro /usr || { echo V29_REMOUNT_RO_FAILED; RC=1; }; fi
 exit "$RC"
}
trap on_exit 0
trap 'exit 1' 1 2 15
$BB mount -o remount,rw /usr
RW=1
$BB mkdir "$B"
$BB cp /usr/lib/libInfraStreamingUsb.so "$B/libInfraStreamingUsb.previous.so"
[ "$(hash "$B/libInfraStreamingUsb.previous.so")" = 27f4f4696c724caa8348edc51c86a517 ]
BACKED=1
$BB cp /usr/share/yuy2-recovery-v28snap/libInfraStreamingUsb.v24p.so "$B/libInfraStreamingUsb.v24p.so"
[ "$(hash "$B/libInfraStreamingUsb.v24p.so")" = 5fde77e394572ebcf420f8941575f6c4 ]
$BB ln /usr/lib/libInfraStreamingUsb.so "$B/libInfraStreamingUsb.previous-inode.so"
$BB cp "$D/rollback.sh" "$B/rollback.sh"
$BB chmod 755 "$B/rollback.sh"
[ "$(hash "$B/rollback.sh")" = 3473352a715f06dc542a344729f80262 ]
$BB sync
$BB cp "$D/yuy2_640_v29full.so" /usr/lib/.yuy2_v29full.new
$BB chmod 755 /usr/lib/.yuy2_v29full.new
[ "$(hash /usr/lib/.yuy2_v29full.new)" = b4c6012cd876210fcfd0cf4b0d6f67e0 ]
$BB mv /usr/lib/.yuy2_v29full.new /usr/lib/yuy2_640_v29full.so
$BB cp "$D/libInfraStreamingUsb.persistent.so" /usr/lib/.libInfraStreamingUsb.v29full.new
$BB chmod 755 /usr/lib/.libInfraStreamingUsb.v29full.new
[ "$(hash /usr/lib/.libInfraStreamingUsb.v29full.new)" = 32a2d064d25720c17dd9a43927d4a835 ]
# Dependency exists and is verified before the streaming pathname is activated.
$BB sync
$BB mv /usr/lib/.libInfraStreamingUsb.v29full.new /usr/lib/libInfraStreamingUsb.so
[ "$(hash /usr/lib/libInfraStreamingUsb.so)" = 32a2d064d25720c17dd9a43927d4a835 ]
[ "$(hash /usr/lib/yuy2_640_v29full.so)" = b4c6012cd876210fcfd0cf4b0d6f67e0 ]
[ "$(hash /usr/lib/yuy2_640_v28snap.so)" = 5dd449056e4da5b7bea072d9e3b65d0b ]
[ "$(hash /usr/lib/yuy2_640_v24p.so)" = 9181ef744955190d04728cf4ef7965c5 ]
[ "$(hash /usr/kmod/usbg_video.ko)" = c1cad400372e26eca729e4b9bc47a237 ]
[ "$(hash /usr/lib/libBizFw.so)" = 6416a5a6780bbe829eb30d85fc8e8dad ]
[ "$(hash /usr/lib/libInfraUsbCmn.so)" = 31308976206a837f6f5c571992d2b499 ]
[ "$(hash /system/av-cam.bin)" = 90096db2c76148f4f9db5d104e5c608c ]
[ "$(hash /setting/DmmConfig.bin)" = 9f197ff9b300e49ab531b6f9e794253e ]
$BB md5sum /usr/lib/libInfraStreamingUsb.so /usr/lib/yuy2_640_v29full.so /usr/lib/yuy2_640_v24p.so /usr/kmod/usbg_video.ko > "$D/installed.md5"
$BB sync
$BB mount -o remount,ro /usr
RW=0
DONE=1
echo V29_FILES_VERIFIED_REBOOT_REQUIRED
