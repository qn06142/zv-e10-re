#!/bin/sh
set -eu
BB=/bin/busybox
RAM=/tmp_bt/zve10-display-v03
DEST=/log/zve10-ram-boot/display-v03
ACTIVE=/log/zve10-ram-boot/boot.ko
sum() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
fail() { echo "$*" >&2;exit 1; }
[ "$(sum /system/av-cam.bin)" = 90096db2c76148f4f9db5d104e5c608c ] || fail 'Camera image changed'
[ "$(sum /usr/lib/viewUnified6.so)" = 9a3cc1f700cbe4a255e29cb5d5b2e2fc ] || fail 'GUI loader changed'
[ "$(sum /log/zve10-ram-loader/payload.bin)" = f8eb38c12734408a0f6d1fe110fa0228 ] || fail 'GUI launcher changed'
[ "$(sum "$ACTIVE")" = 1a40c7e1855aed70d6c8cb4aba8428e3 ] || fail 'Expected resident v02 changed'
[ "$(sum "$RAM/display.ko")" = b466d4f36d9ebaa4cee5a730088f5a86 ] || fail 'Display module staging differs'
[ ! -e "$DEST" ] || fail 'Preserving existing display package'
if $BB grep -q '^zve10_ram_boot ' /proc/modules;then fail 'Test module is already loaded';fi
$BB mkdir "$DEST"
$BB cp "$ACTIVE" "$DEST/previous-runtime-v02.ko"
[ "$(sum "$DEST/previous-runtime-v02.ko")" = 1a40c7e1855aed70d6c8cb4aba8428e3 ] || fail 'Backup differs'
$BB cp "$RAM/display.ko" "$DEST/display.next.ko"
[ "$(sum "$DEST/display.next.ko")" = b466d4f36d9ebaa4cee5a730088f5a86 ] || fail 'Module copy differs'
loaded=0
cleanup() { if [ "$loaded" = 1 ];then $BB rmmod zve10_ram_boot;fi; }
trap cleanup EXIT
$BB insmod "$DEST/display.next.ko"
loaded=1
$BB cat /sys/module/zve10_ram_boot/parameters/state
$BB grep -q '^READY$' /sys/module/zve10_ram_boot/parameters/state || fail 'Stage did not reach READY'
$BB dmesg | $BB grep 'ZVBOOT_STAGE'
$BB rmmod zve10_ram_boot
loaded=0
[ "$(sum "$ACTIVE")" = 1a40c7e1855aed70d6c8cb4aba8428e3 ] || fail 'Active module changed during staging'
$BB mv "$DEST/display.next.ko" "$ACTIVE"
$BB sync
[ "$(sum "$ACTIVE")" = b466d4f36d9ebaa4cee5a730088f5a86 ] || fail 'Installed display module differs'
echo DISPLAY_V03_INSTALLED_STAGE_VERIFIED_NO_GO_SENT
