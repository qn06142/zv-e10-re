#!/bin/sh
set -eu
BB=/bin/busybox
FULL=/tmp/busybox
RAM=/tmp_bt/zve10-ram-boot-20261118
DEST=/log/zve10-ram-boot
PAYLOAD=/log/zve10-ram-loader/payload.bin
NEXT=/log/zve10-ram-loader/payload.next
sum() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
fail() { echo "$*" >&2;exit 1; }
[ "$(sum "$PAYLOAD")" = "02b8ce37814eae81967a78b6e4316af2" ] || fail 'Expected HELLO payload changed'
[ "$(sum /usr/lib/viewUnified6.so)" = 9a3cc1f700cbe4a255e29cb5d5b2e2fc ] || fail 'GUI loader identity differs'
[ "$(sum "$RAM/static-io.ko")" = "432a7a29f2a7f6d729286e9b5b17cf91" ] || fail 'Staged module differs'
[ ! -e "$DEST" ] || fail 'Preserving existing boot package directory'
[ ! -e "$NEXT" ] || fail 'Preserving existing payload staging file'
if $BB grep -q '^zve10_ram_boot ' /proc/modules;then fail 'Boot module must be unloaded';fi
$BB mkdir "$DEST"
$BB cp "$RAM/static-io.ko" "$DEST/boot.ko"
[ "$(sum "$DEST/boot.ko")" = "432a7a29f2a7f6d729286e9b5b17cf91" ] || fail 'Module copy verification failed'
$BB cp "$PAYLOAD" "$DEST/previous-hello.payload.bin"
[ "$(sum "$DEST/previous-hello.payload.bin")" = "02b8ce37814eae81967a78b6e4316af2" ] || fail 'HELLO backup differs'
printf '%s' 'WlZSQU0wMDEBAAAAIAAAACgDAADAAAAAowE7YgEAAAAQtRCxA2gBKwHQACAQvUNoECv60cNoCCv32QAjylwisYRo4lQBMwgr+NGCaAAhAUjRVOvnMU1BUiBIkLUAIYWweEQKRgUnAN8EHjHbaUYPIgMnAN8AIQNGCkYgRgYnAN8EKwLcACAFsJC9EDNrRAP4EByd+AAwUiv00Z34ATBFK/DRnfgCMEEr7NGd+AMwRCvo0Z34BDBZK+TRnfgFMFOxCivf0Z34BgCw+oDwQAna50/w/zDX5wEg1ecAv2cCAAD4tQZG//e4/wEoA0Ym0QAgAUYCRiQnAN9VTBlGfEQE8SwABScA3wMeBdpSSXlEMEa96PhAhOcE8VoBAiIEJwDfACEERgpGGEYGJwDfAiwC0UlJeUTr50lJeUTo5xC5SEl5ROTnR0gAIXhEXTAKRgUnAN+w8QAMAtpDSXlE1+cIRgMiT/SAQSIjT/D/NAVGwCcA3xD1gF8DRgfZYEYpRipGBicA3zlJeUTB5wEkYEZZGcX1gEIDJwDfAh0G0AAoONsG0AVEtfWATwLSATRBLO3RACFgRgpGBicA3z8sINgzLR7ZtfWATxvQGnh/KhjRWnhFKhXRmnhMKhLR2nhGKg/RGnkBKgzRWnkBKgnRGnwBKgbRWnwiuZp8KCoB0dx8VLEYRk/0gEEAIlsnAN8YSXlEfecAJcznF0oYRnpEKUZ5MoAnAN9P9IBBBUYiRhhGWycA3xWxEEl5RGnn//cN/wEoAtEOSXlEYucNSXlEX+cAv8sBAACUAQAATgEAAFABAABYAQAAfwEAAE4BAAApAQAAqQAAAK0AAACJAAAASwAAAE4AAABCT09USU5HAEdPIEVSUgBCT09UIFJEWQBOT1QgUkRZAEdPIE9QRU4ATk8gTU9EAE1BUCBFUlIATU9EIEJBRABNT0QgRVJSAC9zeXMvbW9kdWxlL3p2ZTEwX3JhbV9ib290L3BhcmFtZXRlcnMvc3RhdGUAL3N5cy9tb2R1bGUvenZlMTBfcmFtX2Jvb3QvcGFyYW1ldGVycy9jb21tYW5kAEdPAC9sb2cvenZlMTAtcmFtLWJvb3QvYm9vdC5rbwAAAAAA' > "$RAM/launcher.b64"
$FULL base64 -d "$RAM/launcher.b64" > "$NEXT"
[ "$(sum "$NEXT")" = "f8eb38c12734408a0f6d1fe110fa0228" ] || fail 'Launcher staging differs'
[ "$(sum "$PAYLOAD")" = "02b8ce37814eae81967a78b6e4316af2" ] || fail 'Active payload changed while staging'
$BB mv "$NEXT" "$PAYLOAD"
$BB sync
[ "$(sum "$PAYLOAD")" = "f8eb38c12734408a0f6d1fe110fa0228" ] || fail 'Active launcher verification failed'
echo BOOT_PACKAGE_INSTALLED_NO_GO_SENT
