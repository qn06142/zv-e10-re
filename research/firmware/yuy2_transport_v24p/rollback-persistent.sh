#!/bin/sh
set -e
BB=/bin/busybox
B=/usr/share/yuy2-recovery-v24p
hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
[ "$(hash "$B/libInfraStreamingUsb.baseline.so")" = 19461091c07aa6900829defb0060fcd6 ]
[ "$(hash "$B/usbg_video.baseline.ko")" = 5b59c2e62c80683d754955ab5de0467d ]
case "$(hash /usr/lib/libInfraStreamingUsb.so)" in 5fde77e394572ebcf420f8941575f6c4|19461091c07aa6900829defb0060fcd6) ;; *) echo STREAM_GUARD_FAILED; exit 1;; esac
case "$(hash /usr/kmod/usbg_video.ko)" in c1cad400372e26eca729e4b9bc47a237|5b59c2e62c80683d754955ab5de0467d) ;; *) echo KERNEL_GUARD_FAILED; exit 1;; esac
if [ -e /usr/lib/yuy2_640_v24p.so ]; then [ "$(hash /usr/lib/yuy2_640_v24p.so)" = 9181ef744955190d04728cf4ef7965c5 ]; fi
$BB mount -o remount,rw /usr
trap '$BB sync; $BB mount -o remount,ro /usr' 0
if [ "$(hash /usr/lib/libInfraStreamingUsb.so)" = 5fde77e394572ebcf420f8941575f6c4 ] && [ ! -e "$B/libInfraStreamingUsb.patched-inode.so" ]; then
 $BB ln /usr/lib/libInfraStreamingUsb.so "$B/libInfraStreamingUsb.patched-inode.so"
fi
if [ -e /usr/lib/yuy2_640_v24p.so ] && [ ! -e "$B/yuy2_640_v24p.retired.so" ]; then
 $BB ln /usr/lib/yuy2_640_v24p.so "$B/yuy2_640_v24p.retired.so"
fi
$BB cp "$B/libInfraStreamingUsb.baseline.so" /usr/lib/.libInfraStreamingUsb.yuy2-restore
$BB chmod 755 /usr/lib/.libInfraStreamingUsb.yuy2-restore
$BB mv /usr/lib/.libInfraStreamingUsb.yuy2-restore /usr/lib/libInfraStreamingUsb.so
$BB cp "$B/usbg_video.baseline.ko" /usr/kmod/.usbg_video.yuy2-restore
$BB chmod 644 /usr/kmod/.usbg_video.yuy2-restore
$BB mv /usr/kmod/.usbg_video.yuy2-restore /usr/kmod/usbg_video.ko
if [ -e /usr/lib/yuy2_640_v24p.so ]; then $BB rm /usr/lib/yuy2_640_v24p.so; fi
$BB sync
[ "$(hash /usr/lib/libInfraStreamingUsb.so)" = 19461091c07aa6900829defb0060fcd6 ]
[ "$(hash /usr/kmod/usbg_video.ko)" = 5b59c2e62c80683d754955ab5de0467d ]
echo YUY2_PERSISTENT_BASELINE_RESTORED_REBOOT_REQUIRED
