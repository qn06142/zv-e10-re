#!/bin/sh
set -eu
BB=/bin/busybox
D=/log/yuy2_640_v36vga
B=/usr/share/yuy2-recovery-v36vga
hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
$BB sh "$D/preflight.sh"
[ "$(hash "$D/libInfraStreamingUsb.persistent.so")" = 886445056d2eba99ef62df3a9def5e0f ]
[ "$(hash "$D/yuy2_640_v36vga.so")" = c2e06b5a7a9f1361c4fb2a087d5e8fe2 ]
[ "$(hash "$D/rollback.sh")" = 1e03861d438ff6cc2fd58c1c38aa6e71 ]
$BB sh -n "$D/rollback.sh"
BACKED=0
DONE=0
RW=0
on_exit() {
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
 if [ "$RW" = 1 ]; then $BB mount -o remount,ro /usr || { echo V36_REMOUNT_RO_FAILED; RC=1; }; fi
 exit "$RC"
}
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
[ "$(hash "$B/rollback.sh")" = 1e03861d438ff6cc2fd58c1c38aa6e71 ]
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
