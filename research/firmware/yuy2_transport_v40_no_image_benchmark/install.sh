#!/bin/sh
set -eu
BB=/bin/busybox
D=/log/yuy2_640_v40vga
B=/usr/share/yuy2-recovery-v40vga
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
$BB sh "$D/preflight.sh"
guard "$D/yuy2_640_v40vga.so" 6fbc0edeab4895fbc81fd690e84a5810
guard "$D/libInfraStreamingUsb.persistent.so" cef5b31d4abfb2374a8196e3cc6b904f
guard "$D/usbg_video.ko" 388799d95bbb524ca581c66b077b6dc2
guard "$D/rollback.sh" a48de8b080ad75fc9647980dd1b6deb0
$BB sh -n "$D/rollback.sh"
BACKED=0
DONE=0
RW=0
on_exit() {
 RC=$?
 trap - 0
 set +e
 if [ "$DONE" != 1 ] && [ "$BACKED" = 1 ]; then
  echo V40_INSTALL_FAILED_RESTORING_PAIR
  $BB mount -o remount,rw /usr
  RW=1
  $BB cp "$B/libInfraStreamingUsb.previous.so" /usr/lib/.libInfraStreamingUsb.v40vga.restore
  $BB cp "$B/usbg_video.previous.ko" /usr/kmod/.usbg_video.v40vga.restore
  $BB chmod 755 /usr/lib/.libInfraStreamingUsb.v40vga.restore
  $BB chmod 644 /usr/kmod/.usbg_video.v40vga.restore
  if [ "$(hash /usr/lib/.libInfraStreamingUsb.v40vga.restore)" = cc95285c2e789f186ab5b97c9ba11fcb ] && [ "$(hash /usr/kmod/.usbg_video.v40vga.restore)" = 388799d95bbb524ca581c66b077b6dc2 ]; then
   $BB mv /usr/kmod/.usbg_video.v40vga.restore /usr/kmod/usbg_video.ko
   $BB mv /usr/lib/.libInfraStreamingUsb.v40vga.restore /usr/lib/libInfraStreamingUsb.so
  fi
  if [ "$(hash /usr/lib/libInfraStreamingUsb.so)" = cc95285c2e789f186ab5b97c9ba11fcb ] && [ "$(hash /usr/kmod/usbg_video.ko)" = 388799d95bbb524ca581c66b077b6dc2 ]; then echo V40_FAILURE_RESTORED_PAIR; else echo V40_RECOVERY_REQUIRED; fi
 fi
 $BB sync
 if [ "$RW" = 1 ]; then $BB mount -o remount,ro /usr || { echo V40_REMOUNT_RO_FAILED; RC=1; }; fi
 exit "$RC"
}
trap on_exit 0
trap 'exit 1' 1 2 15
$BB mount -o remount,rw /usr
RW=1
$BB mkdir "$B"
$BB cp /usr/lib/libInfraStreamingUsb.so "$B/libInfraStreamingUsb.previous.so"
$BB cp /usr/kmod/usbg_video.ko "$B/usbg_video.previous.ko"
guard "$B/libInfraStreamingUsb.previous.so" cc95285c2e789f186ab5b97c9ba11fcb
guard "$B/usbg_video.previous.ko" 388799d95bbb524ca581c66b077b6dc2
BACKED=1
$BB cp /usr/share/yuy2-recovery-v29full/libInfraStreamingUsb.v24p.so "$B/libInfraStreamingUsb.v24p.so"
guard "$B/libInfraStreamingUsb.v24p.so" 5fde77e394572ebcf420f8941575f6c4
$BB cp /usr/share/yuy2-recovery-v37vga/usbg_video.previous.ko "$B/usbg_video.v24p.ko"
guard "$B/usbg_video.v24p.ko" c1cad400372e26eca729e4b9bc47a237
$BB cp "$D/rollback.sh" "$B/rollback.sh"
$BB chmod 755 "$B/rollback.sh"
guard "$B/rollback.sh" a48de8b080ad75fc9647980dd1b6deb0
$BB sync
$BB cp "$D/yuy2_640_v40vga.so" /usr/lib/.yuy2_v40vga.new
$BB chmod 755 /usr/lib/.yuy2_v40vga.new
guard /usr/lib/.yuy2_v40vga.new 6fbc0edeab4895fbc81fd690e84a5810
$BB mv /usr/lib/.yuy2_v40vga.new /usr/lib/yuy2_640_v40vga.so
$BB cp "$D/usbg_video.ko" /usr/kmod/.usbg_video.v40vga.new
$BB chmod 644 /usr/kmod/.usbg_video.v40vga.new
guard /usr/kmod/.usbg_video.v40vga.new 388799d95bbb524ca581c66b077b6dc2
$BB cp "$D/libInfraStreamingUsb.persistent.so" /usr/lib/.libInfraStreamingUsb.v40vga.new
$BB chmod 755 /usr/lib/.libInfraStreamingUsb.v40vga.new
guard /usr/lib/.libInfraStreamingUsb.v40vga.new cef5b31d4abfb2374a8196e3cc6b904f
# All staged artifacts and rescue copies exist before activating either path.
$BB sync
$BB mv /usr/kmod/.usbg_video.v40vga.new /usr/kmod/usbg_video.ko
guard /usr/kmod/usbg_video.ko 388799d95bbb524ca581c66b077b6dc2
$BB mv /usr/lib/.libInfraStreamingUsb.v40vga.new /usr/lib/libInfraStreamingUsb.so
guard /usr/lib/libInfraStreamingUsb.so cef5b31d4abfb2374a8196e3cc6b904f
guard /usr/lib/yuy2_640_v40vga.so 6fbc0edeab4895fbc81fd690e84a5810
guard /usr/kmod/usbg_video.ko 388799d95bbb524ca581c66b077b6dc2
guard /usr/lib/yuy2_640_v24p.so 9181ef744955190d04728cf4ef7965c5
$BB md5sum /usr/lib/libInfraStreamingUsb.so /usr/lib/yuy2_640_v40vga.so /usr/kmod/usbg_video.ko "$B/libInfraStreamingUsb.previous.so" "$B/usbg_video.previous.ko" "$B/rollback.sh" > "$D/installed.md5"
$BB sync
$BB mount -o remount,ro /usr
RW=0
DONE=1
echo V40_FILES_VERIFIED_REBOOT_REQUIRED
