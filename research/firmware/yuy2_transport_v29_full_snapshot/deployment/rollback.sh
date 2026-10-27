#!/bin/sh
set -eu
BB=/bin/busybox
B=/usr/share/yuy2-recovery-v29full
hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
[ "$(hash "$B/libInfraStreamingUsb.v24p.so")" = 5fde77e394572ebcf420f8941575f6c4 ]
[ "$(hash /usr/lib/yuy2_640_v24p.so)" = 9181ef744955190d04728cf4ef7965c5 ]
[ "$(hash /usr/kmod/usbg_video.ko)" = c1cad400372e26eca729e4b9bc47a237 ]
P=$($BB pidof im.elf)
case "$P" in ''|*[!0-9]*) echo PROCESS_GUARD_FAILED; exit 1;; esac
if $BB grep -E 'libInfraStreamingUsb|yuy2_640|yc_observer|yc_probe' /proc/$P/maps; then echo COLD_BOOT_BEFORE_ROLLBACK; exit 1; fi
case "$(hash /usr/lib/libInfraStreamingUsb.so)" in 5fde77e394572ebcf420f8941575f6c4|27f4f4696c724caa8348edc51c86a517|32a2d064d25720c17dd9a43927d4a835) ;; *) echo UNKNOWN_STREAM_REFUSED; exit 1;; esac
if [ -e /usr/lib/yuy2_640_v29full.so ]; then [ "$(hash /usr/lib/yuy2_640_v29full.so)" = b4c6012cd876210fcfd0cf4b0d6f67e0 ]; fi
$BB mount -o remount,rw /usr
trap '$BB sync; $BB mount -o remount,ro /usr' 0
$BB cp "$B/libInfraStreamingUsb.v24p.so" /usr/lib/.libInfraStreamingUsb.v29full.restore
$BB chmod 755 /usr/lib/.libInfraStreamingUsb.v29full.restore
[ "$(hash /usr/lib/.libInfraStreamingUsb.v29full.restore)" = 5fde77e394572ebcf420f8941575f6c4 ]
$BB mv /usr/lib/.libInfraStreamingUsb.v29full.restore /usr/lib/libInfraStreamingUsb.so
[ "$(hash /usr/lib/libInfraStreamingUsb.so)" = 5fde77e394572ebcf420f8941575f6c4 ]
# No kernel/RTOS/config/old-module changes. Keep the inert new module for audit.
$BB sync
echo V29_ROLLED_BACK_TO_WORKING_V24P_REBOOT_REQUIRED
