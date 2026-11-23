#!/bin/sh
set -eu
BB=/bin/busybox
B=/usr/share/yuy2-recovery-v32vga
hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
[ "$(hash "$B/libInfraStreamingUsb.previous.so")" = 24bc5972c11f953ad1408f477376a877 ]
[ "$(hash /usr/lib/yuy2_640_v31vga.so)" = 72f800fd8f5e6d943b1d33d173bedeb1 ]
P=$($BB pidof im.elf)
case "$P" in ''|*[!0-9]*) exit 1;; esac
if $BB grep -E 'libInfraStreamingUsb|yuy2_640|yc_observer|yc_probe' /proc/$P/maps; then echo COLD_BOOT_BEFORE_ROLLBACK; exit 1; fi
case "$(hash /usr/lib/libInfraStreamingUsb.so)" in cc3de8f0f0b710e6e2027ac78ea94c50|24bc5972c11f953ad1408f477376a877) ;; *) echo UNKNOWN_STREAM_REFUSED; exit 1;; esac
$BB mount -o remount,rw /usr
trap '$BB sync; $BB mount -o remount,ro /usr' 0
$BB cp "$B/libInfraStreamingUsb.previous.so" /usr/lib/.libInfraStreamingUsb.v32vga.restore
$BB chmod 755 /usr/lib/.libInfraStreamingUsb.v32vga.restore
[ "$(hash /usr/lib/.libInfraStreamingUsb.v32vga.restore)" = 24bc5972c11f953ad1408f477376a877 ]
$BB mv /usr/lib/.libInfraStreamingUsb.v32vga.restore /usr/lib/libInfraStreamingUsb.so
[ "$(hash /usr/lib/libInfraStreamingUsb.so)" = 24bc5972c11f953ad1408f477376a877 ]
$BB sync
echo V32_ROLLED_BACK_TO_PREVIOUS_V31_REBOOT_REQUIRED
