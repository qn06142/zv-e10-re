#!/bin/sh
set -e
BB=/bin/busybox
D=/log/yuy2_640_v24p
B=/usr/share/yuy2-recovery-v24p
hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
[ ! -e /usr/lib/yuy2_640_v24p.so ]
P=$($BB pidof im.elf)
if $BB grep -E 'libInfraStreamingUsb|yuy2_640' /proc/$P/maps; then echo REBOOT_BEFORE_PERSISTENT_INSTALL; exit 1; fi
[ "$(hash /usr/lib/libInfraStreamingUsb.so)" = 19461091c07aa6900829defb0060fcd6 ]
[ "$(hash /usr/lib/libInfraUsbCmn.so)" = 31308976206a837f6f5c571992d2b499 ]
[ "$(hash /system/av-cam.bin)" = 90096db2c76148f4f9db5d104e5c608c ]
[ "$(hash /setting/DmmConfig.bin)" = 9f197ff9b300e49ab531b6f9e794253e ]
[ "$(hash "$D/libInfraStreamingUsb.persistent.so")" = 5fde77e394572ebcf420f8941575f6c4 ]
[ "$(hash "$D/yuy2_640_v24p.so")" = 9181ef744955190d04728cf4ef7965c5 ]
[ "$(hash "$D/usbg_video.ko")" = c1cad400372e26eca729e4b9bc47a237 ]
[ "$(hash "$D/rollback-persistent.sh")" = cd67ea02a57715d823ca7c1baf99499b ]
# Remove only the known temporary overlay; do not unload or modify live code.
if $BB grep -q ' /usr/kmod/usbg_video.ko ' /proc/mounts; then
 [ "$(hash /usr/kmod/usbg_video.ko)" = c1cad400372e26eca729e4b9bc47a237 ]
 $BB umount /usr/kmod/usbg_video.ko
fi
[ "$(hash /usr/kmod/usbg_video.ko)" = 5b59c2e62c80683d754955ab5de0467d ]
$BB mount -o remount,rw /usr
BACKED=0
rollback_install() {
 set +e
 echo PERSISTENT_INSTALL_ROLLBACK
 if [ "$BACKED" = 1 ]; then
  $BB cp "$B/libInfraStreamingUsb.baseline.so" /usr/lib/.libInfraStreamingUsb.yuy2-restore
  $BB mv /usr/lib/.libInfraStreamingUsb.yuy2-restore /usr/lib/libInfraStreamingUsb.so
  $BB cp "$B/usbg_video.baseline.ko" /usr/kmod/.usbg_video.yuy2-restore
  $BB mv /usr/kmod/.usbg_video.yuy2-restore /usr/kmod/usbg_video.ko
  if [ -e /usr/lib/yuy2_640_v24p.so ]; then $BB rm /usr/lib/yuy2_640_v24p.so; fi
 fi
 $BB sync
 $BB mount -o remount,ro /usr
}
trap rollback_install 0
if [ ! -e "$B" ]; then
 $BB mkdir "$B"
 $BB cp /usr/lib/libInfraStreamingUsb.so "$B/libInfraStreamingUsb.baseline.so"
 $BB cp /usr/kmod/usbg_video.ko "$B/usbg_video.baseline.ko"
fi
$BB cp "$D/rollback-persistent.sh" "$B/rollback.sh"
$BB chmod 755 "$B/rollback.sh"
[ "$(hash "$B/libInfraStreamingUsb.baseline.so")" = 19461091c07aa6900829defb0060fcd6 ]
[ "$(hash "$B/usbg_video.baseline.ko")" = 5b59c2e62c80683d754955ab5de0467d ]
BACKED=1
# Retain the old mapped inode when atomically replacing its pathname. Otherwise
# ext2 cannot remount read-only until all old mappings are released.
if [ ! -e "$B/libInfraStreamingUsb.original-inode.so" ]; then
 $BB ln /usr/lib/libInfraStreamingUsb.so "$B/libInfraStreamingUsb.original-inode.so"
fi
[ "$(hash "$B/libInfraStreamingUsb.original-inode.so")" = 19461091c07aa6900829defb0060fcd6 ]
$BB cp "$D/yuy2_640_v24p.so" /usr/lib/.yuy2_640_v24p.new
$BB chmod 755 /usr/lib/.yuy2_640_v24p.new
[ "$(hash /usr/lib/.yuy2_640_v24p.new)" = 9181ef744955190d04728cf4ef7965c5 ]
$BB mv /usr/lib/.yuy2_640_v24p.new /usr/lib/yuy2_640_v24p.so
$BB cp "$D/usbg_video.ko" /usr/kmod/.usbg_video.yuy2-new
$BB chmod 644 /usr/kmod/.usbg_video.yuy2-new
[ "$(hash /usr/kmod/.usbg_video.yuy2-new)" = c1cad400372e26eca729e4b9bc47a237 ]
$BB mv /usr/kmod/.usbg_video.yuy2-new /usr/kmod/usbg_video.ko
# Activate the on-disk dependency last, once both of its components exist.
$BB cp "$D/libInfraStreamingUsb.persistent.so" /usr/lib/.libInfraStreamingUsb.yuy2-new
$BB chmod 755 /usr/lib/.libInfraStreamingUsb.yuy2-new
[ "$(hash /usr/lib/.libInfraStreamingUsb.yuy2-new)" = 5fde77e394572ebcf420f8941575f6c4 ]
$BB mv /usr/lib/.libInfraStreamingUsb.yuy2-new /usr/lib/libInfraStreamingUsb.so
[ "$(hash /usr/lib/libInfraStreamingUsb.so)" = 5fde77e394572ebcf420f8941575f6c4 ]
[ "$(hash /usr/lib/yuy2_640_v24p.so)" = 9181ef744955190d04728cf4ef7965c5 ]
[ "$(hash /usr/kmod/usbg_video.ko)" = c1cad400372e26eca729e4b9bc47a237 ]
[ "$(hash /usr/lib/libInfraUsbCmn.so)" = 31308976206a837f6f5c571992d2b499 ]
$BB sync
$BB mount -o remount,ro /usr
trap - 0
$BB md5sum /usr/lib/libInfraStreamingUsb.so /usr/lib/yuy2_640_v24p.so /usr/kmod/usbg_video.ko /usr/lib/libInfraUsbCmn.so /system/av-cam.bin /setting/DmmConfig.bin > "$D/persistent-files-after.md5"
$BB cat /proc/mounts > "$D/mounts-after-install.txt"
$BB cat "$D/persistent-files-after.md5"
echo V24P_PERSISTENT_FILES_VERIFIED_REBOOT_REQUIRED
