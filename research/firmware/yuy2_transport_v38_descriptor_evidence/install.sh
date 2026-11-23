#!/bin/sh
set -eu
BB=/bin/busybox
D=/log/yuy2_640_v38vga
B=/usr/share/yuy2-recovery-v38vga
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
guard "$D/yuy2_640_v38vga.so" d577730ce4eeec70904cd4fb164580f5
guard "$D/libInfraStreamingUsb.persistent.so" f5d42a08e186b0cf2f519bd105457e08
guard "$D/usbg_video.ko" 388799d95bbb524ca581c66b077b6dc2
guard "$D/rollback.sh" 97ef4b0c55cebfdd2b0417bb6027acd3
$BB sh -n "$D/rollback.sh"
BACKED=0
DONE=0
RW=0
on_exit() {
 RC=$?
 trap - 0
 set +e
 if [ "$DONE" != 1 ] && [ "$BACKED" = 1 ]; then
  echo V38_INSTALL_FAILED_RESTORING_PAIR
  $BB mount -o remount,rw /usr
  RW=1
  $BB cp "$B/libInfraStreamingUsb.previous.so" /usr/lib/.libInfraStreamingUsb.v38vga.restore
  $BB cp "$B/usbg_video.previous.ko" /usr/kmod/.usbg_video.v38vga.restore
  $BB chmod 755 /usr/lib/.libInfraStreamingUsb.v38vga.restore
  $BB chmod 644 /usr/kmod/.usbg_video.v38vga.restore
  if [ "$(hash /usr/lib/.libInfraStreamingUsb.v38vga.restore)" = 277c023942dd4d3d347d9829eaf8be85 ] && [ "$(hash /usr/kmod/.usbg_video.v38vga.restore)" = 388799d95bbb524ca581c66b077b6dc2 ]; then
   $BB mv /usr/kmod/.usbg_video.v38vga.restore /usr/kmod/usbg_video.ko
   $BB mv /usr/lib/.libInfraStreamingUsb.v38vga.restore /usr/lib/libInfraStreamingUsb.so
  fi
  if [ "$(hash /usr/lib/libInfraStreamingUsb.so)" = 277c023942dd4d3d347d9829eaf8be85 ] && [ "$(hash /usr/kmod/usbg_video.ko)" = 388799d95bbb524ca581c66b077b6dc2 ]; then echo V38_FAILURE_RESTORED_PAIR; else echo V38_RECOVERY_REQUIRED; fi
 fi
 $BB sync
 if [ "$RW" = 1 ]; then $BB mount -o remount,ro /usr || { echo V38_REMOUNT_RO_FAILED; RC=1; }; fi
 exit "$RC"
}
trap on_exit 0
trap 'exit 1' 1 2 15
$BB mount -o remount,rw /usr
RW=1
$BB mkdir "$B"
$BB cp /usr/lib/libInfraStreamingUsb.so "$B/libInfraStreamingUsb.previous.so"
$BB cp /usr/kmod/usbg_video.ko "$B/usbg_video.previous.ko"
guard "$B/libInfraStreamingUsb.previous.so" 277c023942dd4d3d347d9829eaf8be85
guard "$B/usbg_video.previous.ko" 388799d95bbb524ca581c66b077b6dc2
BACKED=1
$BB cp /usr/share/yuy2-recovery-v29full/libInfraStreamingUsb.v24p.so "$B/libInfraStreamingUsb.v24p.so"
guard "$B/libInfraStreamingUsb.v24p.so" 5fde77e394572ebcf420f8941575f6c4
$BB cp /usr/share/yuy2-recovery-v37vga/usbg_video.previous.ko "$B/usbg_video.v24p.ko"
guard "$B/usbg_video.v24p.ko" c1cad400372e26eca729e4b9bc47a237
$BB cp "$D/rollback.sh" "$B/rollback.sh"
$BB chmod 755 "$B/rollback.sh"
guard "$B/rollback.sh" 97ef4b0c55cebfdd2b0417bb6027acd3
$BB sync
$BB cp "$D/yuy2_640_v38vga.so" /usr/lib/.yuy2_v38vga.new
$BB chmod 755 /usr/lib/.yuy2_v38vga.new
guard /usr/lib/.yuy2_v38vga.new d577730ce4eeec70904cd4fb164580f5
$BB mv /usr/lib/.yuy2_v38vga.new /usr/lib/yuy2_640_v38vga.so
$BB cp "$D/usbg_video.ko" /usr/kmod/.usbg_video.v38vga.new
$BB chmod 644 /usr/kmod/.usbg_video.v38vga.new
guard /usr/kmod/.usbg_video.v38vga.new 388799d95bbb524ca581c66b077b6dc2
$BB cp "$D/libInfraStreamingUsb.persistent.so" /usr/lib/.libInfraStreamingUsb.v38vga.new
$BB chmod 755 /usr/lib/.libInfraStreamingUsb.v38vga.new
guard /usr/lib/.libInfraStreamingUsb.v38vga.new f5d42a08e186b0cf2f519bd105457e08
# All staged artifacts and rescue copies exist before activating either path.
$BB sync
$BB mv /usr/kmod/.usbg_video.v38vga.new /usr/kmod/usbg_video.ko
guard /usr/kmod/usbg_video.ko 388799d95bbb524ca581c66b077b6dc2
$BB mv /usr/lib/.libInfraStreamingUsb.v38vga.new /usr/lib/libInfraStreamingUsb.so
guard /usr/lib/libInfraStreamingUsb.so f5d42a08e186b0cf2f519bd105457e08
guard /usr/lib/yuy2_640_v38vga.so d577730ce4eeec70904cd4fb164580f5
guard /usr/kmod/usbg_video.ko 388799d95bbb524ca581c66b077b6dc2
guard /usr/lib/yuy2_640_v24p.so 9181ef744955190d04728cf4ef7965c5
$BB md5sum /usr/lib/libInfraStreamingUsb.so /usr/lib/yuy2_640_v38vga.so /usr/kmod/usbg_video.ko "$B/libInfraStreamingUsb.previous.so" "$B/usbg_video.previous.ko" "$B/rollback.sh" > "$D/installed.md5"
$BB sync
$BB mount -o remount,ro /usr
RW=0
DONE=1
echo V38_FILES_VERIFIED_REBOOT_REQUIRED
