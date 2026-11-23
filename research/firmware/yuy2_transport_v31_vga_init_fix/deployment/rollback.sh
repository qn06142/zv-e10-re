#!/bin/sh
set -eu
BB=/bin/busybox
B=/usr/share/yuy2-recovery-v31vga
hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
[ "$(hash "$B/libInfraStreamingUsb.previous.so")" = 2a4c08511526f2b525c57a1d9bac9bad ]
[ "$(hash /usr/lib/yuy2_640_v30vga.so)" = 98acd3ba3d6628e006fe51d88dda25dc ]
P=$($BB pidof im.elf)
case "$P" in ''|*[!0-9]*) exit 1;; esac
if $BB grep -E 'libInfraStreamingUsb|yuy2_640|yc_observer|yc_probe' /proc/$P/maps; then echo COLD_BOOT_BEFORE_ROLLBACK; exit 1; fi
case "$(hash /usr/lib/libInfraStreamingUsb.so)" in 24bc5972c11f953ad1408f477376a877|2a4c08511526f2b525c57a1d9bac9bad) ;; *) echo UNKNOWN_STREAM_REFUSED; exit 1;; esac
$BB mount -o remount,rw /usr
trap '$BB sync; $BB mount -o remount,ro /usr' 0
$BB cp "$B/libInfraStreamingUsb.previous.so" /usr/lib/.libInfraStreamingUsb.v31vga.restore
$BB chmod 755 /usr/lib/.libInfraStreamingUsb.v31vga.restore
[ "$(hash /usr/lib/.libInfraStreamingUsb.v31vga.restore)" = 2a4c08511526f2b525c57a1d9bac9bad ]
$BB mv /usr/lib/.libInfraStreamingUsb.v31vga.restore /usr/lib/libInfraStreamingUsb.so
[ "$(hash /usr/lib/libInfraStreamingUsb.so)" = 2a4c08511526f2b525c57a1d9bac9bad ]
$BB sync
echo V31_ROLLED_BACK_TO_PREVIOUS_V30_REBOOT_REQUIRED
