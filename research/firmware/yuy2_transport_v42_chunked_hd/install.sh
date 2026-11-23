#!/bin/sh
set -eu
BB=/bin/busybox
D=/log/yuy2_1080_v41hd
B=/usr/share/yuy2-recovery-v42chunk
hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
guard() { [ "$(hash "$1")" = "$2" ] || { echo "HASH_FAILED:$1"; exit 1; }; }
P=$($BB pidof im.elf)
case "$P" in ''|*[!0-9]*) exit 1;; esac
if $BB grep -E 'libInfraStreamingUsb|yuy2_|yc_observer|yc_probe' /proc/$P/maps; then echo COLD_BOOT_REQUIRED; exit 1; fi
[ "$($BB cat /proc/ssboot/state)" = idle ]
guard /usr/lib/libInfraStreamingUsb.so cef5b31d4abfb2374a8196e3cc6b904f
guard /usr/kmod/usbg_video.ko 388799d95bbb524ca581c66b077b6dc2
guard /setting/DmmConfig.bin 9f197ff9b300e49ab531b6f9e794253e
guard "$D/yuy2_1080_v42chunk.so" b155dceb58c031e63dd8b16c13bb3619
guard "$D/libInfraStreamingUsb.v42.so" f6f769095b8cd32e23e57e9b71db5408
guard "$D/usbg_video.v42.ko" 702b82f347b6fc25e8d46ddba1836743
[ ! -e "$B" ]
[ ! -e /usr/lib/yuy2_1080_v42chunk.so ]
"$D/space-check.elf"
DONE=0
finish() {
 RC=$?
 trap - 0
 set +e
 $BB sync
 $BB mount -o remount,ro /usr || RC=1
 if [ "$DONE" != 1 ]; then echo V42_INSTALL_INCOMPLETE_NO_AUTOMATIC_RESTORE; fi
 exit "$RC"
}
$BB mount -o remount,rw /usr
trap finish 0
trap 'exit 1' 1 2 15
$BB mkdir "$B"
$BB cp /usr/lib/libInfraStreamingUsb.so "$B/libInfraStreamingUsb.before.so"
$BB cp /usr/kmod/usbg_video.ko "$B/usbg_video.before.ko"
guard "$B/libInfraStreamingUsb.before.so" cef5b31d4abfb2374a8196e3cc6b904f
guard "$B/usbg_video.before.ko" 388799d95bbb524ca581c66b077b6dc2
$BB cp "$D/yuy2_1080_v42chunk.so" /usr/lib/.yuy2_v42.new
$BB cp "$D/libInfraStreamingUsb.v42.so" /usr/lib/.libInfraStreamingUsb.v42.new
$BB cp "$D/usbg_video.v42.ko" /usr/kmod/.usbg_video.v42.new
$BB chmod 755 /usr/lib/.yuy2_v42.new /usr/lib/.libInfraStreamingUsb.v42.new
$BB chmod 644 /usr/kmod/.usbg_video.v42.new
guard /usr/lib/.yuy2_v42.new b155dceb58c031e63dd8b16c13bb3619
guard /usr/lib/.libInfraStreamingUsb.v42.new f6f769095b8cd32e23e57e9b71db5408
guard /usr/kmod/.usbg_video.v42.new 702b82f347b6fc25e8d46ddba1836743
$BB mkdir -p /log/yuy2_1080_v42chunk
$BB sync
$BB mv /usr/lib/.yuy2_v42.new /usr/lib/yuy2_1080_v42chunk.so
$BB mv /usr/kmod/.usbg_video.v42.new /usr/kmod/usbg_video.ko
$BB mv /usr/lib/.libInfraStreamingUsb.v42.new /usr/lib/libInfraStreamingUsb.so
guard /usr/lib/yuy2_1080_v42chunk.so b155dceb58c031e63dd8b16c13bb3619
guard /usr/kmod/usbg_video.ko 702b82f347b6fc25e8d46ddba1836743
guard /usr/lib/libInfraStreamingUsb.so f6f769095b8cd32e23e57e9b71db5408
guard /setting/DmmConfig.bin 9f197ff9b300e49ab531b6f9e794253e
$BB sync
DONE=1
echo V42_PATCH_INSTALLED_CONFIG_UNCHANGED
