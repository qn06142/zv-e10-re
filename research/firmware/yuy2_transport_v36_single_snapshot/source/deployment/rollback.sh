#!/bin/sh
set -eu
BB=/bin/busybox
B=/usr/share/yuy2-recovery-v36vga
hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
[ "$(hash "$B/libInfraStreamingUsb.previous.so")" = c16af3a036529b89d23fa4ccfd059ec3 ]
[ "$(hash /usr/lib/yuy2_640_v35vga.so)" = e6b9fa6947a21e5a6a1603e070a1d00f ]
P=$($BB pidof im.elf)
case "$P" in ''|*[!0-9]*) exit 1;; esac
if $BB grep -E 'libInfraStreamingUsb|yuy2_640|yc_observer|yc_probe' /proc/$P/maps; then echo COLD_BOOT_BEFORE_ROLLBACK; exit 1; fi
case "$(hash /usr/lib/libInfraStreamingUsb.so)" in 886445056d2eba99ef62df3a9def5e0f|c16af3a036529b89d23fa4ccfd059ec3) ;; *) echo UNKNOWN_STREAM_REFUSED; exit 1;; esac
$BB mount -o remount,rw /usr
trap '$BB sync; $BB mount -o remount,ro /usr' 0
$BB cp "$B/libInfraStreamingUsb.previous.so" /usr/lib/.libInfraStreamingUsb.v36vga.restore
$BB chmod 755 /usr/lib/.libInfraStreamingUsb.v36vga.restore
[ "$(hash /usr/lib/.libInfraStreamingUsb.v36vga.restore)" = c16af3a036529b89d23fa4ccfd059ec3 ]
$BB mv /usr/lib/.libInfraStreamingUsb.v36vga.restore /usr/lib/libInfraStreamingUsb.so
[ "$(hash /usr/lib/libInfraStreamingUsb.so)" = c16af3a036529b89d23fa4ccfd059ec3 ]
$BB sync
echo V36_ROLLED_BACK_TO_PREVIOUS_V35_REBOOT_REQUIRED
