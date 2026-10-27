#!/bin/sh
set -eu
BB=/bin/busybox
hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
guard() { [ "$(hash "$1")" = "$2" ] || { echo "HASH_GUARD_FAILED:$1"; exit 1; }; }
P=$($BB pidof im.elf)
case "$P" in ''|*[!0-9]*) echo PROCESS_GUARD_FAILED; exit 1;; esac
if $BB grep -E 'libInfraStreamingUsb|yuy2_640|yc_observer|yc_probe' /proc/$P/maps; then echo COLD_BOOT_REQUIRED; exit 1; fi
if $BB grep -E ' /usr/(lib/libInfraStreamingUsb.so|lib/libInfraUsbCmn.so|lib/libBizFw.so|kmod/usbg_video.ko) ' /proc/mounts; then echo OVERLAY_GUARD_FAILED; exit 1; fi
guard /usr/lib/libInfraStreamingUsb.so c3aa9b92ea6c05ce78aa7894e8dfe35a
guard /usr/lib/yuy2_640_v27snap.so ec185c27deb53f80f6f5a40d9a8f95f1
guard /usr/share/yuy2-recovery-v27snap/libInfraStreamingUsb.v24p.so 5fde77e394572ebcf420f8941575f6c4
guard /usr/lib/yuy2_640_v24p.so 9181ef744955190d04728cf4ef7965c5
guard /usr/kmod/usbg_video.ko c1cad400372e26eca729e4b9bc47a237
guard /usr/lib/libInfraUsbCmn.so 31308976206a837f6f5c571992d2b499
guard /usr/lib/libBizFw.so 6416a5a6780bbe829eb30d85fc8e8dad
guard /system/av-cam.bin 90096db2c76148f4f9db5d104e5c608c
guard /setting/DmmConfig.bin 9f197ff9b300e49ab531b6f9e794253e
[ -x /usr/share/yuy2-recovery-v24p/rollback.sh ]
[ ! -e /usr/lib/yuy2_640_v28snap.so ]
[ ! -e /usr/share/yuy2-recovery-v28snap ]
[ ! -e /usr/lib/.yuy2_v28snap.new ]
[ ! -e /usr/lib/.libInfraStreamingUsb.v28snap.new ]
SPACE=${1:-/log/yuy2_640_v28snap/space-check.elf}
guard "$SPACE" c2c8b809405bf52e3a7fa8df88aa95eb
$BB chmod 755 "$SPACE"
"$SPACE"
$BB cat /proc/uptime
$BB md5sum /usr/lib/libInfraStreamingUsb.so /usr/lib/yuy2_640_v24p.so /usr/kmod/usbg_video.ko /usr/lib/libBizFw.so /usr/lib/libInfraUsbCmn.so /system/av-cam.bin /setting/DmmConfig.bin
$BB cat /proc/udm/dmm_units
echo DMM_LISTING_IS_NOT_PROOF_OF_ACTIVE_STREAM_SOURCE
echo V28_PREFLIGHT_OK
