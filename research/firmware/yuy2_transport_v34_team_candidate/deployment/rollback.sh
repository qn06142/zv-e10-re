#!/bin/sh
set -eu
BB=/bin/busybox
B=/usr/share/yuy2-recovery-v34vga
hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
[ "$(hash "$B/libInfraStreamingUsb.previous.so")" = 909c4ffadc9e5972b25101529d5f8773 ]
[ "$(hash /usr/lib/yuy2_640_v33vga.so)" = 87ddc16bd8e0774926e5eb6d16165d20 ]
P=$($BB pidof im.elf)
case "$P" in ''|*[!0-9]*) exit 1;; esac
if $BB grep -E 'libInfraStreamingUsb|yuy2_640|yc_observer|yc_probe' /proc/$P/maps; then echo COLD_BOOT_BEFORE_ROLLBACK; exit 1; fi
case "$(hash /usr/lib/libInfraStreamingUsb.so)" in ca3cbbc5947caf3373ebe451343fb926|909c4ffadc9e5972b25101529d5f8773) ;; *) echo UNKNOWN_STREAM_REFUSED; exit 1;; esac
$BB mount -o remount,rw /usr
trap '$BB sync; $BB mount -o remount,ro /usr' 0
$BB cp "$B/libInfraStreamingUsb.previous.so" /usr/lib/.libInfraStreamingUsb.v34vga.restore
$BB chmod 755 /usr/lib/.libInfraStreamingUsb.v34vga.restore
[ "$(hash /usr/lib/.libInfraStreamingUsb.v34vga.restore)" = 909c4ffadc9e5972b25101529d5f8773 ]
$BB mv /usr/lib/.libInfraStreamingUsb.v34vga.restore /usr/lib/libInfraStreamingUsb.so
[ "$(hash /usr/lib/libInfraStreamingUsb.so)" = 909c4ffadc9e5972b25101529d5f8773 ]
$BB sync
echo V34_ROLLED_BACK_TO_PREVIOUS_V33_REBOOT_REQUIRED
