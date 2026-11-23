#!/bin/sh
set -eu
BB=/bin/busybox
D=/log/yuy2_640_v37vga
B=/usr/share/tmp-fat-recovery-20261029
hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
[ "$(hash /usr/kmod/kikilog.ko)" = 51337167a2ab42d53557c2cce210c987 ]
[ "$(hash "$D/kikilog.tmpnofile.ko")" = 8af7cfd952dbdd47b4f468de6c7d385e ]
[ "$(hash /usr/lib/libInfraStreamingUsb.so)" = 886445056d2eba99ef62df3a9def5e0f ]
[ "$(hash /usr/kmod/usbg_video.ko)" = c1cad400372e26eca729e4b9bc47a237 ]
[ ! -e "$B" ]
[ ! -e /usr/kmod/.kikilog.tmpnofile.new ]
BACKED=0
DONE=0
RW=0
finish() {
 RC=$?
 trap - 0
 set +e
 if [ "$DONE" != 1 ] && [ "$BACKED" = 1 ]; then
  $BB mount -o remount,rw /usr
  RW=1
  $BB cp "$B/kikilog.original.ko" /usr/kmod/.kikilog.tmpnofile.restore
  if [ "$(hash /usr/kmod/.kikilog.tmpnofile.restore)" = 51337167a2ab42d53557c2cce210c987 ]; then
   $BB chmod 644 /usr/kmod/.kikilog.tmpnofile.restore
   $BB mv /usr/kmod/.kikilog.tmpnofile.restore /usr/kmod/kikilog.ko
  fi
  if [ "$(hash /usr/kmod/kikilog.ko)" = 51337167a2ab42d53557c2cce210c987 ]; then echo V37_TEMP_LOG_FAILURE_RESTORED_ORIGINAL; else echo V37_TEMP_LOG_RECOVERY_REQUIRED; fi
 fi
 $BB sync
 if [ "$RW" = 1 ]; then $BB mount -o remount,ro /usr || RC=1; fi
 exit "$RC"
}
trap finish 0
trap 'exit 1' 1 2 15
$BB mount -o remount,rw /usr
RW=1
$BB mkdir "$B"
$BB cp /usr/kmod/kikilog.ko "$B/kikilog.original.ko"
[ "$(hash "$B/kikilog.original.ko")" = 51337167a2ab42d53557c2cce210c987 ]
BACKED=1
$BB cp "$D/kikilog.tmpnofile.ko" /usr/kmod/.kikilog.tmpnofile.new
$BB chmod 644 /usr/kmod/.kikilog.tmpnofile.new
[ "$(hash /usr/kmod/.kikilog.tmpnofile.new)" = 8af7cfd952dbdd47b4f468de6c7d385e ]
$BB mv /usr/kmod/.kikilog.tmpnofile.new /usr/kmod/kikilog.ko
[ "$(hash /usr/kmod/kikilog.ko)" = 8af7cfd952dbdd47b4f468de6c7d385e ]
$BB sync
$BB mount -o remount,ro /usr
RW=0
DONE=1
echo V37_TEMP_LOG_DRIVER_VERIFIED_REBOOT_REQUIRED
