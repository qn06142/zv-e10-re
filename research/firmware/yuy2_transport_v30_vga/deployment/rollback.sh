#!/bin/sh
set -eu
BB=/bin/busybox
B=/usr/share/yuy2-recovery-v30vga
hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
[ "$(hash "$B/libInfraStreamingUsb.previous.so")" = 32a2d064d25720c17dd9a43927d4a835 ]
[ "$(hash /usr/lib/yuy2_640_v29full.so)" = b4c6012cd876210fcfd0cf4b0d6f67e0 ]
P=$($BB pidof im.elf)
case "$P" in ''|*[!0-9]*) exit 1;; esac
if $BB grep -E 'libInfraStreamingUsb|yuy2_640|yc_observer|yc_probe' /proc/$P/maps; then echo COLD_BOOT_BEFORE_ROLLBACK; exit 1; fi
case "$(hash /usr/lib/libInfraStreamingUsb.so)" in 2a4c08511526f2b525c57a1d9bac9bad|32a2d064d25720c17dd9a43927d4a835) ;; *) echo UNKNOWN_STREAM_REFUSED; exit 1;; esac
$BB mount -o remount,rw /usr
trap '$BB sync; $BB mount -o remount,ro /usr' 0
$BB cp "$B/libInfraStreamingUsb.previous.so" /usr/lib/.libInfraStreamingUsb.v30vga.restore
$BB chmod 755 /usr/lib/.libInfraStreamingUsb.v30vga.restore
[ "$(hash /usr/lib/.libInfraStreamingUsb.v30vga.restore)" = 32a2d064d25720c17dd9a43927d4a835 ]
$BB mv /usr/lib/.libInfraStreamingUsb.v30vga.restore /usr/lib/libInfraStreamingUsb.so
[ "$(hash /usr/lib/libInfraStreamingUsb.so)" = 32a2d064d25720c17dd9a43927d4a835 ]
$BB sync
echo V30_ROLLED_BACK_TO_PREVIOUS_V29_REBOOT_REQUIRED
