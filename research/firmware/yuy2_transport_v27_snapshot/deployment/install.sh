#!/bin/sh
set -eu
BB=/bin/busybox
D=/log/yuy2_640_v27snap
B=/usr/share/yuy2-recovery-v27snap
hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
$BB sh "$D/preflight.sh"
[ "$(hash "$D/libInfraStreamingUsb.persistent.so")" = c3aa9b92ea6c05ce78aa7894e8dfe35a ]
[ "$(hash "$D/yuy2_640_v27snap.so")" = ec185c27deb53f80f6f5a40d9a8f95f1 ]
[ "$(hash "$D/rollback.sh")" = 8bf7f491412fd697c9984a0107ebb1fc ]
$BB sh -n "$D/rollback.sh"
BACKED=0
DONE=0
RW=0
on_exit() {
 RC=$?
 trap - 0
 set +e
 if [ "$DONE" != 1 ] && [ "$BACKED" = 1 ]; then
  echo V27_INSTALL_FAILED_RESTORING_V24P
  $BB cp "$B/libInfraStreamingUsb.v24p.so" /usr/lib/.libInfraStreamingUsb.v27snap.restore
  $BB chmod 755 /usr/lib/.libInfraStreamingUsb.v27snap.restore
  if [ "$(hash /usr/lib/.libInfraStreamingUsb.v27snap.restore)" = 5fde77e394572ebcf420f8941575f6c4 ]; then
   $BB mv /usr/lib/.libInfraStreamingUsb.v27snap.restore /usr/lib/libInfraStreamingUsb.so
  fi
  if [ "$(hash /usr/lib/libInfraStreamingUsb.so)" = 5fde77e394572ebcf420f8941575f6c4 ]; then echo V27_FAILURE_RESTORED_V24P; else echo V27_RECOVERY_REQUIRED; fi
 fi
 $BB sync
 if [ "$RW" = 1 ]; then $BB mount -o remount,ro /usr || { echo V27_REMOUNT_RO_FAILED; RC=1; }; fi
 exit "$RC"
}
trap on_exit 0
trap 'exit 1' 1 2 15
$BB mount -o remount,rw /usr
RW=1
$BB mkdir "$B"
$BB cp /usr/lib/libInfraStreamingUsb.so "$B/libInfraStreamingUsb.v24p.so"
[ "$(hash "$B/libInfraStreamingUsb.v24p.so")" = 5fde77e394572ebcf420f8941575f6c4 ]
BACKED=1
$BB ln /usr/lib/libInfraStreamingUsb.so "$B/libInfraStreamingUsb.v24p-inode.so"
$BB cp "$D/rollback.sh" "$B/rollback.sh"
$BB chmod 755 "$B/rollback.sh"
[ "$(hash "$B/rollback.sh")" = 8bf7f491412fd697c9984a0107ebb1fc ]
$BB sync
$BB cp "$D/yuy2_640_v27snap.so" /usr/lib/.yuy2_v27snap.new
$BB chmod 755 /usr/lib/.yuy2_v27snap.new
[ "$(hash /usr/lib/.yuy2_v27snap.new)" = ec185c27deb53f80f6f5a40d9a8f95f1 ]
$BB mv /usr/lib/.yuy2_v27snap.new /usr/lib/yuy2_640_v27snap.so
$BB cp "$D/libInfraStreamingUsb.persistent.so" /usr/lib/.libInfraStreamingUsb.v27snap.new
$BB chmod 755 /usr/lib/.libInfraStreamingUsb.v27snap.new
[ "$(hash /usr/lib/.libInfraStreamingUsb.v27snap.new)" = c3aa9b92ea6c05ce78aa7894e8dfe35a ]
# Dependency exists and is verified before the streaming pathname is activated.
$BB sync
$BB mv /usr/lib/.libInfraStreamingUsb.v27snap.new /usr/lib/libInfraStreamingUsb.so
[ "$(hash /usr/lib/libInfraStreamingUsb.so)" = c3aa9b92ea6c05ce78aa7894e8dfe35a ]
[ "$(hash /usr/lib/yuy2_640_v27snap.so)" = ec185c27deb53f80f6f5a40d9a8f95f1 ]
[ "$(hash /usr/lib/yuy2_640_v24p.so)" = 9181ef744955190d04728cf4ef7965c5 ]
[ "$(hash /usr/kmod/usbg_video.ko)" = c1cad400372e26eca729e4b9bc47a237 ]
[ "$(hash /usr/lib/libBizFw.so)" = 6416a5a6780bbe829eb30d85fc8e8dad ]
[ "$(hash /usr/lib/libInfraUsbCmn.so)" = 31308976206a837f6f5c571992d2b499 ]
[ "$(hash /system/av-cam.bin)" = 90096db2c76148f4f9db5d104e5c608c ]
[ "$(hash /setting/DmmConfig.bin)" = 9f197ff9b300e49ab531b6f9e794253e ]
$BB md5sum /usr/lib/libInfraStreamingUsb.so /usr/lib/yuy2_640_v27snap.so /usr/lib/yuy2_640_v24p.so /usr/kmod/usbg_video.ko > "$D/installed.md5"
$BB sync
$BB mount -o remount,ro /usr
RW=0
DONE=1
echo V27_FILES_VERIFIED_REBOOT_REQUIRED
