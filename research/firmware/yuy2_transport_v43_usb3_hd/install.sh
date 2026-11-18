#!/bin/sh
set -eu
BB=/bin/busybox
D=/log/yuy2_1080_v43chunk
B=/usr/share/yuy2-recovery-v43chunk

hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
guard() { [ "$(hash "$1")" = "$2" ] || { echo "HASH_FAILED:$1 (got $(hash "$1"), expected $2)"; exit 1; }; }

P=$($BB pidof im.elf)
case "$P" in ''|*[!0-9]*) echo "INVALID_PID:$P"; exit 1;; esac
if $BB grep -E 'libInfraStreamingUsb|yuy2_|yc_observer|yc_probe' /proc/$P/maps; then echo COLD_BOOT_REQUIRED; exit 1; fi
[ "$($BB cat /proc/ssboot/state)" = idle ]

# Accept stock factory, v42, or v43 streaming library baseline
ORIG_STREAM_MD5="$(hash /usr/lib/libInfraStreamingUsb.so)"
if [ "$ORIG_STREAM_MD5" != "cef5b31d4abfb2374a8196e3cc6b904f" ] && [ "$ORIG_STREAM_MD5" != "f6f769095b8cd32e23e57e9b71db5408" ] && [ "$ORIG_STREAM_MD5" != "4c5deb4a89474c0a3b65356f034a5d9e" ]; then
    echo "UNEXPECTED_STREAM_ORIG:$ORIG_STREAM_MD5"
    exit 1
fi

# Accept stock factory, v42, or v43 kernel module baseline
ORIG_KMOD_MD5="$(hash /usr/kmod/usbg_video.ko)"
if [ "$ORIG_KMOD_MD5" != "388799d95bbb524ca581c66b077b6dc2" ] && [ "$ORIG_KMOD_MD5" != "702b82f347b6fc25e8d46ddba1836743" ] && [ "$ORIG_KMOD_MD5" != "9ded6930932e7db541247c4b158b93fc" ]; then
    echo "UNEXPECTED_KMOD_ORIG:$ORIG_KMOD_MD5"
    exit 1
fi

# Guard critical factory DMM configuration - MUST NEVER BE ALTERED
guard /setting/DmmConfig.bin 9f197ff9b300e49ab531b6f9e794253e

# Guard Revision staged artifacts
guard "$D/yuy2_1080_v43chunk.so" c5c382ee23062131a99fd9855577f42c
guard "$D/libInfraStreamingUsb.v43.so" 4c5deb4a89474c0a3b65356f034a5d9e
guard "$D/usbg_video.v43.ko" 9ded6930932e7db541247c4b158b93fc

if [ -x "$D/space-check.elf" ]; then
    "$D/space-check.elf"
fi

DONE=0
finish() {
    RC=$?
    trap - 0
    set +e
    $BB sync
    $BB mount -o remount,ro /usr || RC=1
    if [ "$DONE" != 1 ]; then echo V43_INSTALL_INCOMPLETE_NO_AUTOMATIC_RESTORE; fi
    exit "$RC"
}

$BB mount -o remount,rw /usr
trap finish 0
trap 'exit 1' 1 2 15

if [ ! -d "$B" ]; then
    $BB mkdir -p "$B"
    $BB cp /usr/lib/libInfraStreamingUsb.so "$B/libInfraStreamingUsb.before.so"
    $BB cp /usr/kmod/usbg_video.ko "$B/usbg_video.before.ko"
    guard "$B/libInfraStreamingUsb.before.so" "$ORIG_STREAM_MD5"
    guard "$B/usbg_video.before.ko" "$ORIG_KMOD_MD5"
fi

# Stage new files with temporary filenames
$BB cp "$D/yuy2_1080_v43chunk.so" /usr/lib/.yuy2_v43.new
$BB cp "$D/libInfraStreamingUsb.v43.so" /usr/lib/.libInfraStreamingUsb.v43.new
$BB cp "$D/usbg_video.v43.ko" /usr/kmod/.usbg_video.v43.new

$BB chmod 755 /usr/lib/.yuy2_v43.new /usr/lib/.libInfraStreamingUsb.v43.new
$BB chmod 644 /usr/kmod/.usbg_video.v43.new

guard /usr/lib/.yuy2_v43.new c5c382ee23062131a99fd9855577f42c
guard /usr/lib/.libInfraStreamingUsb.v43.new 4c5deb4a89474c0a3b65356f034a5d9e
guard /usr/kmod/.usbg_video.v43.new 9ded6930932e7db541247c4b158b93fc

$BB mkdir -p /log/yuy2_1080_v43chunk
$BB sync

# Atomic rename to active locations
$BB mv /usr/lib/.yuy2_v43.new /usr/lib/yuy2_1080_v43chunk.so
$BB mv /usr/kmod/.usbg_video.v43.new /usr/kmod/usbg_video.ko
$BB mv /usr/lib/.libInfraStreamingUsb.v43.new /usr/lib/libInfraStreamingUsb.so

# Verify target installation hashes
guard /usr/lib/yuy2_1080_v43chunk.so c5c382ee23062131a99fd9855577f42c
guard /usr/kmod/usbg_video.ko 9ded6930932e7db541247c4b158b93fc
guard /usr/lib/libInfraStreamingUsb.so 4c5deb4a89474c0a3b65356f034a5d9e

# Confirm factory DMM configuration is completely intact
guard /setting/DmmConfig.bin 9f197ff9b300e49ab531b6f9e794253e

$BB sync
DONE=1
echo V43_PATCH_INSTALLED_CONFIG_UNCHANGED
