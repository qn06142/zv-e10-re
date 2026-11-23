#!/bin/sh
set -eu
BB=/bin/busybox
B=/usr/share/yuy2-recovery-v33vga
hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
[ "$(hash "$B/libInfraStreamingUsb.previous.so")" = cc3de8f0f0b710e6e2027ac78ea94c50 ]
[ "$(hash /usr/lib/yuy2_640_v32vga.so)" = de59485d1ad155711d81cd592ed5b821 ]
P=$($BB pidof im.elf)
case "$P" in ''|*[!0-9]*) exit 1;; esac
if $BB grep -E 'libInfraStreamingUsb|yuy2_640|yc_observer|yc_probe' /proc/$P/maps; then echo COLD_BOOT_BEFORE_ROLLBACK; exit 1; fi
case "$(hash /usr/lib/libInfraStreamingUsb.so)" in 909c4ffadc9e5972b25101529d5f8773|cc3de8f0f0b710e6e2027ac78ea94c50) ;; *) echo UNKNOWN_STREAM_REFUSED; exit 1;; esac
$BB mount -o remount,rw /usr
trap '$BB sync; $BB mount -o remount,ro /usr' 0
$BB cp "$B/libInfraStreamingUsb.previous.so" /usr/lib/.libInfraStreamingUsb.v33vga.restore
$BB chmod 755 /usr/lib/.libInfraStreamingUsb.v33vga.restore
[ "$(hash /usr/lib/.libInfraStreamingUsb.v33vga.restore)" = cc3de8f0f0b710e6e2027ac78ea94c50 ]
$BB mv /usr/lib/.libInfraStreamingUsb.v33vga.restore /usr/lib/libInfraStreamingUsb.so
[ "$(hash /usr/lib/libInfraStreamingUsb.so)" = cc3de8f0f0b710e6e2027ac78ea94c50 ]
$BB sync
echo V33_ROLLED_BACK_TO_PREVIOUS_V32_REBOOT_REQUIRED
