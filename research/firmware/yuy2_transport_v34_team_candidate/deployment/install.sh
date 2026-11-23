#!/bin/sh
set -eu
BB=/bin/busybox
D=/log/yuy2_640_v34vga
B=/usr/share/yuy2-recovery-v34vga
hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
$BB sh "$D/preflight.sh"
[ "$(hash "$D/libInfraStreamingUsb.persistent.so")" = ca3cbbc5947caf3373ebe451343fb926 ]
[ "$(hash "$D/yuy2_640_v34vga.so")" = ac565b4060a7062745d3bd22037d5410 ]
[ "$(hash "$D/rollback.sh")" = e7463d98ace84c1b5db7ee95eae3defe ]
$BB sh -n "$D/rollback.sh"
BACKED=0
DONE=0
RW=0
on_exit() {
 RC=$?
 trap - 0
 set +e
 if [ "$DONE" != 1 ] && [ "$BACKED" = 1 ]; then
  echo V34_INSTALL_FAILED_RESTORING_PREVIOUS
  $BB cp "$B/libInfraStreamingUsb.previous.so" /usr/lib/.libInfraStreamingUsb.v34vga.restore
  $BB chmod 755 /usr/lib/.libInfraStreamingUsb.v34vga.restore
  if [ "$(hash /usr/lib/.libInfraStreamingUsb.v34vga.restore)" = 909c4ffadc9e5972b25101529d5f8773 ]; then
   $BB mv /usr/lib/.libInfraStreamingUsb.v34vga.restore /usr/lib/libInfraStreamingUsb.so
  fi
  if [ "$(hash /usr/lib/libInfraStreamingUsb.so)" = 909c4ffadc9e5972b25101529d5f8773 ]; then echo V34_FAILURE_RESTORED_PREVIOUS; else echo V34_RECOVERY_REQUIRED; fi
 fi
 $BB sync
 if [ "$RW" = 1 ]; then $BB mount -o remount,ro /usr || { echo V34_REMOUNT_RO_FAILED; RC=1; }; fi
 exit "$RC"
}
trap on_exit 0
trap 'exit 1' 1 2 15
$BB mount -o remount,rw /usr
RW=1
$BB mkdir "$B"
$BB cp /usr/lib/libInfraStreamingUsb.so "$B/libInfraStreamingUsb.previous.so"
[ "$(hash "$B/libInfraStreamingUsb.previous.so")" = 909c4ffadc9e5972b25101529d5f8773 ]
BACKED=1
$BB cp /usr/share/yuy2-recovery-v29full/libInfraStreamingUsb.v24p.so "$B/libInfraStreamingUsb.v24p.so"
[ "$(hash "$B/libInfraStreamingUsb.v24p.so")" = 5fde77e394572ebcf420f8941575f6c4 ]
$BB ln /usr/lib/libInfraStreamingUsb.so "$B/libInfraStreamingUsb.previous-inode.so"
$BB cp "$D/rollback.sh" "$B/rollback.sh"
$BB chmod 755 "$B/rollback.sh"
[ "$(hash "$B/rollback.sh")" = e7463d98ace84c1b5db7ee95eae3defe ]
$BB sync
$BB cp "$D/yuy2_640_v34vga.so" /usr/lib/.yuy2_v34vga.new
$BB chmod 755 /usr/lib/.yuy2_v34vga.new
[ "$(hash /usr/lib/.yuy2_v34vga.new)" = ac565b4060a7062745d3bd22037d5410 ]
$BB mv /usr/lib/.yuy2_v34vga.new /usr/lib/yuy2_640_v34vga.so
$BB cp "$D/libInfraStreamingUsb.persistent.so" /usr/lib/.libInfraStreamingUsb.v34vga.new
$BB chmod 755 /usr/lib/.libInfraStreamingUsb.v34vga.new
[ "$(hash /usr/lib/.libInfraStreamingUsb.v34vga.new)" = ca3cbbc5947caf3373ebe451343fb926 ]
# Dependency exists and is verified before the streaming pathname is activated.
$BB sync
$BB mv /usr/lib/.libInfraStreamingUsb.v34vga.new /usr/lib/libInfraStreamingUsb.so
[ "$(hash /usr/lib/libInfraStreamingUsb.so)" = ca3cbbc5947caf3373ebe451343fb926 ]
[ "$(hash /usr/lib/yuy2_640_v34vga.so)" = ac565b4060a7062745d3bd22037d5410 ]
[ "$(hash /usr/lib/yuy2_640_v28snap.so)" = 5dd449056e4da5b7bea072d9e3b65d0b ]
[ "$(hash /usr/lib/yuy2_640_v24p.so)" = 9181ef744955190d04728cf4ef7965c5 ]
[ "$(hash /usr/kmod/usbg_video.ko)" = c1cad400372e26eca729e4b9bc47a237 ]
[ "$(hash /usr/lib/libBizFw.so)" = 6416a5a6780bbe829eb30d85fc8e8dad ]
[ "$(hash /usr/lib/libInfraUsbCmn.so)" = 31308976206a837f6f5c571992d2b499 ]
[ "$(hash /system/av-cam.bin)" = 90096db2c76148f4f9db5d104e5c608c ]
[ "$(hash /setting/DmmConfig.bin)" = 9f197ff9b300e49ab531b6f9e794253e ]
$BB md5sum /usr/lib/libInfraStreamingUsb.so /usr/lib/yuy2_640_v34vga.so /usr/lib/yuy2_640_v24p.so /usr/kmod/usbg_video.ko > "$D/installed.md5"
$BB sync
$BB mount -o remount,ro /usr
RW=0
DONE=1
echo V34_FILES_VERIFIED_REBOOT_REQUIRED
