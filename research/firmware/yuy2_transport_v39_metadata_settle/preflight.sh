#!/bin/sh
set -eu
BB=/bin/busybox
D=/log/yuy2_640_v39vga
B=/usr/share/yuy2-recovery-v39vga
hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
guard() { [ "$(hash "$1")" = "$2" ] || { echo "HASH_GUARD_FAILED:$1"; exit 1; }; }
cold() {
 P=$($BB pidof im.elf)
 case "$P" in ''|*[!0-9]*) echo PROCESS_GUARD_FAILED; exit 1;; esac
 [ -r /proc/$P/maps ]
 if $BB grep -E 'libInfraStreamingUsb|yuy2_640|yc_observer|yc_probe' /proc/$P/maps; then echo COLD_BOOT_REQUIRED; exit 1; fi
 [ -r /proc/mounts ]
 if $BB grep -E ' /usr/(lib/libInfraStreamingUsb.so|lib/libInfraUsbCmn.so|lib/libBizFw.so|lib/dataflowInfraFramework.so|.local/kmod/usbg_video.ko) ' /proc/mounts; then echo OVERLAY_GUARD_FAILED; exit 1; fi
}
cold
guard /usr/lib/libInfraStreamingUsb.so f5d42a08e186b0cf2f519bd105457e08
guard /usr/kmod/usbg_video.ko 388799d95bbb524ca581c66b077b6dc2
guard /usr/lib/yuy2_640_v38vga.so d577730ce4eeec70904cd4fb164580f5
guard /usr/lib/yuy2_640_v24p.so 9181ef744955190d04728cf4ef7965c5
guard /usr/share/yuy2-recovery-v29full/libInfraStreamingUsb.v24p.so 5fde77e394572ebcf420f8941575f6c4
guard /usr/share/yuy2-recovery-v37vga/usbg_video.previous.ko c1cad400372e26eca729e4b9bc47a237
guard /usr/kmod/kikilog.ko 51337167a2ab42d53557c2cce210c987
guard /usr/kmod/dmm.ko 15c8f7807b291c0af3c77fe55848577f
guard /usr/lib/libInfraUsbCmn.so 31308976206a837f6f5c571992d2b499
guard /usr/lib/libObj.so 0b4be3fb599b539c69c782bd400dd8e9
guard /usr/lib/libBizFw.so 6416a5a6780bbe829eb30d85fc8e8dad
guard /usr/lib/dataflowInfraFramework.so f70f50f931e9c2cf415cc2728e324f60
guard /lib/libpthread.so.0 09cb541e6e785dd6bfeb76d74f29f5d2
guard /system/av-cam.bin 90096db2c76148f4f9db5d104e5c608c
guard /setting/DmmConfig.bin 9f197ff9b300e49ab531b6f9e794253e
[ ! -e /usr/lib/yuy2_640_v39vga.so ]
[ ! -e "$B" ]
for F in /usr/lib/.yuy2_v39vga.new /usr/lib/.libInfraStreamingUsb.v39vga.new /usr/kmod/.usbg_video.v39vga.new /usr/lib/.libInfraStreamingUsb.v39vga.restore /usr/kmod/.usbg_video.v39vga.restore; do [ ! -e "$F" ]; done
[ ! -e "$D/rejected-source.yc38" ]
SPACE=${1:-/log/yuy2_640_v39vga/space-check.elf}
guard "$SPACE" c2c8b809405bf52e3a7fa8df88aa95eb
$BB chmod 755 "$SPACE"
"$SPACE"
$BB cat /proc/uptime
echo V39_PREFLIGHT_OK
