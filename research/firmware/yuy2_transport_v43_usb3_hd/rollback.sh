#!/bin/sh
set -eu
BB=/bin/busybox
B=/usr/share/yuy2-recovery-v43chunk

hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
guard() { [ "$(hash "$1")" = "$2" ] || { echo "HASH_FAILED:$1 (got $(hash "$1"), expected $2)"; exit 1; }; }

[ -d "$B" ] || { echo "NO_BACKUP_DIR:$B"; exit 1; }
[ -f "$B/libInfraStreamingUsb.before.so" ] || { echo "MISSING_STREAM_BACKUP"; exit 1; }
[ -f "$B/usbg_video.before.ko" ] || { echo "MISSING_KMOD_BACKUP"; exit 1; }

ORIG_STREAM_MD5="$(hash "$B/libInfraStreamingUsb.before.so")"
ORIG_KMOD_MD5="$(hash "$B/usbg_video.before.ko")"

DONE=0
finish() {
    RC=$?
    trap - 0
    set +e
    $BB sync
    $BB mount -o remount,ro /usr || RC=1
    if [ "$DONE" != 1 ]; then echo V43_ROLLBACK_INCOMPLETE; fi
    exit "$RC"
}

$BB mount -o remount,rw /usr
trap finish 0
trap 'exit 1' 1 2 15

# Restore backup copies
$BB cp "$B/libInfraStreamingUsb.before.so" /usr/lib/.libInfraStreamingUsb.restore
$BB cp "$B/usbg_video.before.ko" /usr/kmod/.usbg_video.restore
$BB chmod 755 /usr/lib/.libInfraStreamingUsb.restore
$BB chmod 644 /usr/kmod/.usbg_video.restore

guard /usr/lib/.libInfraStreamingUsb.restore "$ORIG_STREAM_MD5"
guard /usr/kmod/.usbg_video.restore "$ORIG_KMOD_MD5"

# Remove v43 shared library
$BB rm -f /usr/lib/yuy2_1080_v43chunk.so

# Move back to production paths
$BB mv /usr/lib/.libInfraStreamingUsb.restore /usr/lib/libInfraStreamingUsb.so
$BB mv /usr/kmod/.usbg_video.restore /usr/kmod/usbg_video.ko

guard /usr/lib/libInfraStreamingUsb.so "$ORIG_STREAM_MD5"
guard /usr/kmod/usbg_video.ko "$ORIG_KMOD_MD5"
guard /setting/DmmConfig.bin 9f197ff9b300e49ab531b6f9e794253e

# Clean up recovery directory
$BB rm -rf "$B"
$BB sync
DONE=1
echo V43_ROLLBACK_SUCCESSFUL
