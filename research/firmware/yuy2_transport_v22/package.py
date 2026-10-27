"""Package the offline candidate and a guarded, unexecuted RAM install script."""
from pathlib import Path
import hashlib,json

import argparse
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--repo',type=Path,required=True)
ap.add_argument('--output',type=Path,required=True)
args=ap.parse_args();out=args.output.resolve();root=args.repo.resolve()
manifest=json.loads((out/'manifest.json').read_text())
cfg=(root/'dumps/camera_2025/usr/setting/DmmConfig.bin').read_bytes()
manifest['config_md5']=hashlib.md5(cfg).hexdigest()
manifest['required_firmware_md5']={
 'av-cam.bin':'90096db2c76148f4f9db5d104e5c608c',
 'libInfraStreamingUsb.so':'19461091c07aa6900829defb0060fcd6',
 'libInfraUsbCmn.so':'31308976206a837f6f5c571992d2b499'}
manifest['verification']=json.loads((out/'verification.json').read_text())
bootstrap=json.loads((out/'bootstrap-verification.json').read_text())
assert manifest['verification']['passed']==42 and len(bootstrap)==4
manifest['bootstrap_verification_cases']=len(bootstrap)
manifest['status']='OFFLINE_VERIFIED_NOT_HARDWARE_TESTED'
names=['yuy2_640_v22.so','checked_mempatch.elf','bootstrap-before.bin','bootstrap-after.bin','prepare-before.bin','prepare-after.bin']
script='''set -e
BB=/bin/busybox
D=/log/yuy2_640_v22
P=$($BB pidof im.elf)
[ -n "$P" ]
hash() { $BB md5sum "$1" | $BB cut -d ' ' -f 1; }
[ "$(hash /system/av-cam.bin)" = 90096db2c76148f4f9db5d104e5c608c ]
[ "$(hash /usr/lib/libInfraStreamingUsb.so)" = 19461091c07aa6900829defb0060fcd6 ]
[ "$(hash /usr/lib/libInfraUsbCmn.so)" = 31308976206a837f6f5c571992d2b499 ]
'''
script+=f'[ "$(hash /setting/DmmConfig.bin)" = {manifest["config_md5"]} ]\n'
script+='''$BB grep -q '^0a73d000-.*libInfraStreamingUsb.so' /proc/$P/maps
$BB grep -q '^04834000-.*libInfraUsbCmn.so' /proc/$P/maps
$BB grep -q '^040ba000-.*libdl-2.11.2.so' /proc/$P/maps
if $BB grep -q 'yuy2_640' /proc/$P/maps; then
  echo A_YUY2_MODULE_IS_ALREADY_LOADED; exit 1
fi
'''
for name in names:script+=f'[ "$(hash "$D/{name}")" = {manifest["files"][name]["md5"]} ]\n'
script+='''$BB chmod 755 "$D/checked_mempatch.elf"
"$D/checked_mempatch.elf" "$P" 0a7460c0 "$D/bootstrap-before.bin" "$D/bootstrap-after.bin" arm-volatile
if ! "$D/checked_mempatch.elf" "$P" 0a745d00 "$D/prepare-before.bin" "$D/prepare-after.bin" arm-volatile; then
  "$D/checked_mempatch.elf" "$P" 0a7460c0 "$D/bootstrap-after.bin" "$D/bootstrap-before.bin" arm-volatile
  exit 1
fi
echo YUY2_V22_RAM_BOOTSTRAP_ARMED
'''
sb=int(manifest['stream_base'],0)
script=script.replace('0a73d000',format(sb,'08x')).replace('0a7460c0',format(sb+0x90c0,'08x')).replace('0a745d00',format(sb+0x8d00,'08x'))
(out/'install-ram.sh').write_text(script,encoding='ascii',newline='\n')
(out/'upload-files.json').write_text(json.dumps([[str(out/n),'/log/yuy2_640_v22/'+n] for n in names],indent=2)+'\n')
manifest['not_installed']=True
manifest['removal']='Real reboot clears RAM hooks; power-switch hibernation may retain them.'
manifest['limitations']=[
 'No hardware frames demonstrated for this revision; 0x276 allocation succeeded in revision 2.1.',
 'Five source attempts have four 150ms delays plus the original IPC helper timeouts (up to 3s per request); not a 750ms hard deadline.',
 'The successful 0x276 source and mapping remain reserved for the entire RAM module lifetime; reboot releases them. Failed partial initialization still rolls back.',
 'OSAL notification failure is retried five times and logged, but unavailable firmware queues cannot be repaired by this patch.',
 'The pre-start Ready hook and synchronous helper run on the original event thread; hardware validation must confirm mode-switch ordering.']
for name in ['yuy2_640.c','install-ram.sh']:
 b=(out/name).read_bytes();manifest['files'][name]={'bytes':len(b),'md5':hashlib.md5(b).hexdigest(),'sha256':hashlib.sha256(b).hexdigest()}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Packaged verified revision 2.2 candidate; no camera operations performed')
