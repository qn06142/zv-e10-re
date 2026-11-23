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
guard "$B/libInfraStreamingUsb.previous.so" f5d42a08e186b0cf2f519bd105457e08
guard "$B/usbg_video.previous.ko" 388799d95bbb524ca581c66b077b6dc2
MODE=${1:-previous}
case "$MODE" in
 previous) SRC="$B/libInfraStreamingUsb.previous.so"; EXPECT=f5d42a08e186b0cf2f519bd105457e08; KSRC="$B/usbg_video.previous.ko"; KEXPECT=388799d95bbb524ca581c66b077b6dc2; guard /usr/lib/yuy2_640_v38vga.so d577730ce4eeec70904cd4fb164580f5;;
 --bars) SRC="$B/libInfraStreamingUsb.v24p.so"; EXPECT=5fde77e394572ebcf420f8941575f6c4; KSRC="$B/usbg_video.v24p.ko"; KEXPECT=c1cad400372e26eca729e4b9bc47a237; guard "$KSRC" c1cad400372e26eca729e4b9bc47a237; guard "$SRC" 5fde77e394572ebcf420f8941575f6c4; guard /usr/lib/yuy2_640_v24p.so 9181ef744955190d04728cf4ef7965c5;;
 *) echo BAD_ROLLBACK_MODE; exit 1;;
esac
case "$(hash /usr/lib/libInfraStreamingUsb.so)" in cc95285c2e789f186ab5b97c9ba11fcb|f5d42a08e186b0cf2f519bd105457e08|5fde77e394572ebcf420f8941575f6c4) ;; *) echo UNKNOWN_WRAPPER_REFUSED; exit 1;; esac
case "$(hash /usr/kmod/usbg_video.ko)" in 388799d95bbb524ca581c66b077b6dc2|388799d95bbb524ca581c66b077b6dc2|c1cad400372e26eca729e4b9bc47a237) ;; *) echo UNKNOWN_KERNEL_REFUSED; exit 1;; esac
RW=0
finish() { RC=$?; trap - 0; set +e; $BB sync; if [ "$RW" = 1 ]; then $BB mount -o remount,ro /usr || RC=1; fi; exit "$RC"; }
trap finish 0
trap 'exit 1' 1 2 15
$BB mount -o remount,rw /usr
RW=1
$BB cp "$SRC" /usr/lib/.libInfraStreamingUsb.v39vga.restore
$BB cp "$KSRC" /usr/kmod/.usbg_video.v39vga.restore
$BB chmod 755 /usr/lib/.libInfraStreamingUsb.v39vga.restore
$BB chmod 644 /usr/kmod/.usbg_video.v39vga.restore
guard /usr/lib/.libInfraStreamingUsb.v39vga.restore "$EXPECT"
guard /usr/kmod/.usbg_video.v39vga.restore "$KEXPECT"
$BB mv /usr/kmod/.usbg_video.v39vga.restore /usr/kmod/usbg_video.ko
$BB mv /usr/lib/.libInfraStreamingUsb.v39vga.restore /usr/lib/libInfraStreamingUsb.so
guard /usr/kmod/usbg_video.ko "$KEXPECT"
guard /usr/lib/libInfraStreamingUsb.so "$EXPECT"
$BB sync
$BB mount -o remount,ro /usr
RW=0
echo V39_ROLLBACK_VERIFIED_${MODE}_REBOOT_REQUIRED
