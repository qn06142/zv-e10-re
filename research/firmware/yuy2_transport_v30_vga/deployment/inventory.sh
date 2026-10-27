set -e
BB=/bin/busybox
/usr/bin/ulogio.elf lstop 131 > /log/yuy2_640_v30vga/logger-stop.txt 2>&1 || true
/usr/bin/ulogio.elf filter on 131 error
/usr/bin/ulogio.elf filter on 135 error
/usr/bin/ulogio.elf filter on 136 error
for DIR in /log/yuy2_640* /log/yc_* /log/video_tab_* /log/menu_crash_* /log/usb_debug_*; do
 [ -d "$DIR" ] || continue
 for F in "$DIR"/* "$DIR"/*/* "$DIR"/*/*/*; do
  [ -f "$F" ] || continue
  case "${F##*/}" in *.log|biz*.bin|debug*.bin|klog*.bin|trace*.bin|*ulogio*.txt|*logger-stop*.txt) $BB md5sum "$F";; esac
 done
done > /log/yuy2_640_v30vga/cleanup-inventory.md5
for F in /tmp/opengate_trace/*.log /tmp/v27-old-logger-stop.txt /tmp/yc-retest-log-guard.out; do
 [ -f "$F" ] || continue
 $BB md5sum "$F"
done >> /log/yuy2_640_v30vga/cleanup-inventory.md5
echo V30_CAPTURE_INVENTORY_OK
