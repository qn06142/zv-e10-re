"""Assemble guarded three-file revision 3.9 package offline. Never contacts camera."""
from pathlib import Path
import hashlib,json,shutil,zipfile
W=Path(__file__).resolve().parent;ROOT=W.parent.parent;O=ROOT/'outputs/vga-v39';P=O/'flash-package';P.mkdir(exist_ok=True)
md=lambda p:hashlib.md5(p.read_bytes()).hexdigest()
OLD='f5d42a08e186b0cf2f519bd105457e08';OM='d577730ce4eeec70904cd4fb164580f5';OK='388799d95bbb524ca581c66b077b6dc2'
NW=md(O/'build/libInfraStreamingUsb.so');NM=md(O/'build/yuy2_640_v39vga.so');NK=md(O/'usbg_video.ko')
assert NW=='cc95285c2e789f186ab5b97c9ba11fcb' and NM=='0fede3f034f6cfca755f9f678d73ffe8' and NK=='388799d95bbb524ca581c66b077b6dc2'
STABLE='5fde77e394572ebcf420f8941575f6c4'
KSTABLE='c1cad400372e26eca729e4b9bc47a237'
STATIC={
 '/usr/lib/yuy2_640_v38vga.so':OM,
 '/usr/lib/yuy2_640_v24p.so':'9181ef744955190d04728cf4ef7965c5',
 '/usr/share/yuy2-recovery-v29full/libInfraStreamingUsb.v24p.so':STABLE,
 '/usr/share/yuy2-recovery-v37vga/usbg_video.previous.ko':KSTABLE,
 '/usr/kmod/kikilog.ko':'51337167a2ab42d53557c2cce210c987',
 '/usr/kmod/dmm.ko':'15c8f7807b291c0af3c77fe55848577f',
 '/usr/lib/libInfraUsbCmn.so':'31308976206a837f6f5c571992d2b499',
 '/usr/lib/libObj.so':'0b4be3fb599b539c69c782bd400dd8e9',
 '/usr/lib/libBizFw.so':'6416a5a6780bbe829eb30d85fc8e8dad',
 '/usr/lib/dataflowInfraFramework.so':'f70f50f931e9c2cf415cc2728e324f60',
 '/lib/libpthread.so.0':'09cb541e6e785dd6bfeb76d74f29f5d2',
 '/system/av-cam.bin':'90096db2c76148f4f9db5d104e5c608c',
 '/setting/DmmConfig.bin':'9f197ff9b300e49ab531b6f9e794253e',
}
COMMON='''#!/bin/sh
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
 if $BB grep -E ' /usr/(lib/libInfraStreamingUsb.so|lib/libInfraUsbCmn.so|lib/libBizFw.so|lib/dataflowInfraFramework.so|kmod/usbg_video.ko) ' /proc/mounts; then echo OVERLAY_GUARD_FAILED; exit 1; fi
}
'''
pre=COMMON+f'''cold
guard /usr/lib/libInfraStreamingUsb.so {OLD}
guard /usr/kmod/usbg_video.ko {OK}
'''+''.join(f'guard {p} {h}\n' for p,h in STATIC.items())+'''[ ! -e /usr/lib/yuy2_640_v39vga.so ]
[ ! -e "$B" ]
for F in /usr/lib/.yuy2_v39vga.new /usr/lib/.libInfraStreamingUsb.v39vga.new /usr/kmod/.usbg_video.v39vga.new /usr/lib/.libInfraStreamingUsb.v39vga.restore /usr/kmod/.usbg_video.v39vga.restore; do [ ! -e "$F" ]; done
[ ! -e "$D/rejected-source.yc38" ]
SPACE=${1:-/log/yuy2_640_v39vga/space-check.elf}
guard "$SPACE" c2c8b809405bf52e3a7fa8df88aa95eb
$BB chmod 755 "$SPACE"
"$SPACE"
$BB cat /proc/uptime
echo V39_PREFLIGHT_OK
'''
# Rollback selects a matched wrapper+kernel pair and verifies both staged copies
# before replacing either pathname. Stable bars are an explicit alternative.
rollback=COMMON+f'''cold
guard "$B/libInfraStreamingUsb.previous.so" {OLD}
guard "$B/usbg_video.previous.ko" {OK}
MODE=${{1:-previous}}
case "$MODE" in
 previous) SRC="$B/libInfraStreamingUsb.previous.so"; EXPECT={OLD}; KSRC="$B/usbg_video.previous.ko"; KEXPECT={OK}; guard /usr/lib/yuy2_640_v38vga.so {OM};;
 --bars) SRC="$B/libInfraStreamingUsb.v24p.so"; EXPECT={STABLE}; KSRC="$B/usbg_video.v24p.ko"; KEXPECT={KSTABLE}; guard "$KSRC" {KSTABLE}; guard "$SRC" {STABLE}; guard /usr/lib/yuy2_640_v24p.so 9181ef744955190d04728cf4ef7965c5;;
 *) echo BAD_ROLLBACK_MODE; exit 1;;
esac
case "$(hash /usr/lib/libInfraStreamingUsb.so)" in {NW}|{OLD}|{STABLE}) ;; *) echo UNKNOWN_WRAPPER_REFUSED; exit 1;; esac
case "$(hash /usr/kmod/usbg_video.ko)" in {NK}|{OK}|{KSTABLE}) ;; *) echo UNKNOWN_KERNEL_REFUSED; exit 1;; esac
RW=0
finish() {{ RC=$?; trap - 0; set +e; $BB sync; if [ "$RW" = 1 ]; then $BB mount -o remount,ro /usr || RC=1; fi; exit "$RC"; }}
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
echo V39_ROLLBACK_VERIFIED_${{MODE}}_REBOOT_REQUIRED
'''
RH=hashlib.md5(rollback.encode()).hexdigest()
install=COMMON+f'''$BB sh "$D/preflight.sh"
guard "$D/yuy2_640_v39vga.so" {NM}
guard "$D/libInfraStreamingUsb.persistent.so" {NW}
guard "$D/usbg_video.ko" {NK}
guard "$D/rollback.sh" {RH}
$BB sh -n "$D/rollback.sh"
BACKED=0
DONE=0
RW=0
on_exit() {{
 RC=$?
 trap - 0
 set +e
 if [ "$DONE" != 1 ] && [ "$BACKED" = 1 ]; then
  echo V39_INSTALL_FAILED_RESTORING_PAIR
  $BB mount -o remount,rw /usr
  RW=1
  $BB cp "$B/libInfraStreamingUsb.previous.so" /usr/lib/.libInfraStreamingUsb.v39vga.restore
  $BB cp "$B/usbg_video.previous.ko" /usr/kmod/.usbg_video.v39vga.restore
  $BB chmod 755 /usr/lib/.libInfraStreamingUsb.v39vga.restore
  $BB chmod 644 /usr/kmod/.usbg_video.v39vga.restore
  if [ "$(hash /usr/lib/.libInfraStreamingUsb.v39vga.restore)" = {OLD} ] && [ "$(hash /usr/kmod/.usbg_video.v39vga.restore)" = {OK} ]; then
   $BB mv /usr/kmod/.usbg_video.v39vga.restore /usr/kmod/usbg_video.ko
   $BB mv /usr/lib/.libInfraStreamingUsb.v39vga.restore /usr/lib/libInfraStreamingUsb.so
  fi
  if [ "$(hash /usr/lib/libInfraStreamingUsb.so)" = {OLD} ] && [ "$(hash /usr/kmod/usbg_video.ko)" = {OK} ]; then echo V39_FAILURE_RESTORED_PAIR; else echo V39_RECOVERY_REQUIRED; fi
 fi
 $BB sync
 if [ "$RW" = 1 ]; then $BB mount -o remount,ro /usr || {{ echo V39_REMOUNT_RO_FAILED; RC=1; }}; fi
 exit "$RC"
}}
trap on_exit 0
trap 'exit 1' 1 2 15
$BB mount -o remount,rw /usr
RW=1
$BB mkdir "$B"
$BB cp /usr/lib/libInfraStreamingUsb.so "$B/libInfraStreamingUsb.previous.so"
$BB cp /usr/kmod/usbg_video.ko "$B/usbg_video.previous.ko"
guard "$B/libInfraStreamingUsb.previous.so" {OLD}
guard "$B/usbg_video.previous.ko" {OK}
BACKED=1
$BB cp /usr/share/yuy2-recovery-v29full/libInfraStreamingUsb.v24p.so "$B/libInfraStreamingUsb.v24p.so"
guard "$B/libInfraStreamingUsb.v24p.so" {STABLE}
$BB cp /usr/share/yuy2-recovery-v37vga/usbg_video.previous.ko "$B/usbg_video.v24p.ko"
guard "$B/usbg_video.v24p.ko" {KSTABLE}
$BB cp "$D/rollback.sh" "$B/rollback.sh"
$BB chmod 755 "$B/rollback.sh"
guard "$B/rollback.sh" {RH}
$BB sync
$BB cp "$D/yuy2_640_v39vga.so" /usr/lib/.yuy2_v39vga.new
$BB chmod 755 /usr/lib/.yuy2_v39vga.new
guard /usr/lib/.yuy2_v39vga.new {NM}
$BB mv /usr/lib/.yuy2_v39vga.new /usr/lib/yuy2_640_v39vga.so
$BB cp "$D/usbg_video.ko" /usr/kmod/.usbg_video.v39vga.new
$BB chmod 644 /usr/kmod/.usbg_video.v39vga.new
guard /usr/kmod/.usbg_video.v39vga.new {NK}
$BB cp "$D/libInfraStreamingUsb.persistent.so" /usr/lib/.libInfraStreamingUsb.v39vga.new
$BB chmod 755 /usr/lib/.libInfraStreamingUsb.v39vga.new
guard /usr/lib/.libInfraStreamingUsb.v39vga.new {NW}
# All staged artifacts and rescue copies exist before activating either path.
$BB sync
$BB mv /usr/kmod/.usbg_video.v39vga.new /usr/kmod/usbg_video.ko
guard /usr/kmod/usbg_video.ko {NK}
$BB mv /usr/lib/.libInfraStreamingUsb.v39vga.new /usr/lib/libInfraStreamingUsb.so
guard /usr/lib/libInfraStreamingUsb.so {NW}
guard /usr/lib/yuy2_640_v39vga.so {NM}
guard /usr/kmod/usbg_video.ko {NK}
guard /usr/lib/yuy2_640_v24p.so 9181ef744955190d04728cf4ef7965c5
$BB md5sum /usr/lib/libInfraStreamingUsb.so /usr/lib/yuy2_640_v39vga.so /usr/kmod/usbg_video.ko "$B/libInfraStreamingUsb.previous.so" "$B/usbg_video.previous.ko" "$B/rollback.sh" > "$D/installed.md5"
$BB sync
$BB mount -o remount,ro /usr
RW=0
DONE=1
echo V39_FILES_VERIFIED_REBOOT_REQUIRED
'''
for n,s in [('preflight.sh',pre),('rollback.sh',rollback),('install.sh',install)]: (P/n).write_bytes(s.encode('ascii'))
for src,n in [(O/'build/yuy2_640_v39vga.so','yuy2_640_v39vga.so'),(O/'build/libInfraStreamingUsb.so','libInfraStreamingUsb.persistent.so'),(O/'usbg_video.ko','usbg_video.ko'),(ROOT/'outputs/vga-v36/flash-package/space-check.elf','space-check.elf')]:shutil.copyfile(src,P/n)
manifest=json.loads((O/'build/manifest.json').read_text());manifest['files']={}
manifest.update(installed_baseline=dict(revision='3.8',wrapper_md5=OLD,module_md5=OM,kernel_md5=OK),rollback='previous restores failing 3.8 pair; --bars restores exact stable 2.4p wrapper and separate c1cad400 kernel',deployment='NOT_INSTALLED',hardware_verified=False,kernel_unchanged_from_revision_37=True,diagnostic_only=False)
for n in ['preflight.sh','rollback.sh','install.sh','yuy2_640_v39vga.so','libInfraStreamingUsb.persistent.so','usbg_video.ko','space-check.elf']:
 d=(P/n).read_bytes();manifest['files'][n]=dict(bytes=len(d),md5=hashlib.md5(d).hexdigest(),sha256=hashlib.sha256(d).hexdigest())
(P/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
shutil.copyfile(W/'README.md',P/'README.md')
(P/'evidence').mkdir(exist_ok=True)
for src in [*O.glob('*verification.json'),O/'build/persistent-verification.json',O/'build/isa-verification.json']:
 shutil.copyfile(src,P/'evidence'/src.name)
print(json.dumps(manifest,indent=2))
