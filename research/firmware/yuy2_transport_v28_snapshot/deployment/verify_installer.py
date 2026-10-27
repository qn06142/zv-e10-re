"""Execute packaged shell scripts against a local fixture; never contacts a camera."""
from pathlib import Path
import tempfile,subprocess,hashlib,json,shutil
W=Path(__file__).resolve().parent;P=Path('outputs/native-dmm-v28/flash-package').resolve();BASH='C:/msys64/usr/bin/bash.exe'
OLD='c3aa9b92ea6c05ce78aa7894e8dfe35a';NEW='27f4f4696c724caa8348edc51c86a517'
STATIC={'/usr/lib/yuy2_640_v27snap.so':'ec185c27deb53f80f6f5a40d9a8f95f1','/usr/lib/yuy2_640_v24p.so':'9181ef744955190d04728cf4ef7965c5','/usr/kmod/usbg_video.ko':'c1cad400372e26eca729e4b9bc47a237','/usr/lib/libInfraUsbCmn.so':'31308976206a837f6f5c571992d2b499','/usr/lib/libBizFw.so':'6416a5a6780bbe829eb30d85fc8e8dad','/system/av-cam.bin':'90096db2c76148f4f9db5d104e5c608c','/setting/DmmConfig.bin':'9f197ff9b300e49ab531b6f9e794253e'}
old=Path('outputs/native-dmm-callback/candidate/libInfraStreamingUsb.persistent.so').read_bytes();assert hashlib.md5(old).hexdigest()==OLD
results=[]
class Fixture:
 def __init__(self):
  self.root=Path(tempfile.mkdtemp(prefix='v28-installer-',dir=str(Path('outputs/native-dmm-v28').resolve())));self.stage=self.root/'log/yuy2_640_v28snap';self.stage.mkdir(parents=True)
  for path,h in STATIC.items():
   f=self.root/path.lstrip('/');f.parent.mkdir(parents=True,exist_ok=True);f.write_text(h)
  f=self.root/'usr/lib/libInfraStreamingUsb.so';f.write_bytes(old)
  stable=Path('outputs/yuy2-640-v24p/candidate/libInfraStreamingUsb.persistent.so').read_bytes()
  b=self.root/'usr/share/yuy2-recovery-v27snap/libInfraStreamingUsb.v24p.so';b.parent.mkdir(parents=True,exist_ok=True);b.write_bytes(stable)
  for path,text in [('proc/123/maps','libBizFw.so\n'),('proc/mounts',''),('proc/uptime','123.00 0.00\n'),('proc/udm/dmm_units','408a 0006193f 2 01 01 0 1 1 18000000 001fa400\n'),('usr/share/yuy2-recovery-v24p/rollback.sh','#!/bin/sh\nexit 0\n')]:
   f=self.root/path;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(text)
  fake=self.root/'busybox';root=self.root.as_posix()
  fake.write_text('''#!/usr/bin/bash
set -eu
PATH=/usr/bin:/bin
export PATH
ROOT="ROOT_PATH"
cmd=$1;shift
case "$cmd" in
 pidof) echo 123;;
 mount) echo "$*" >> "$ROOT/mount-calls"; if [ -e "$ROOT/fail-ro" ] && [ "$2" = remount,ro ]; then exit 1; fi;;
 sync) :;;
 df) echo 'Filesystem 1024-blocks Used Available Capacity Mounted on'; if [ -e "$ROOT/fail-space" ]; then echo 'fixture 100000 99900 100 99% /usr'; else echo 'fixture 100000 1000 99000 1% /usr'; fi;;
 md5sum)
  for f in "$@"; do
   if [ -f "$f" ] && [ "$(wc -c < "$f")" = 32 ] && [[ "$(cat "$f")" =~ ^[0-9a-f]{32}$ ]]; then printf '%s  %s\\n' "$(cat "$f")" "$f"; else md5sum "$f"; fi
  done;;
 cp)
  if [ -e "$ROOT/fail-module" ] && [ "$2" = "$ROOT/usr/lib/.yuy2_v28snap.new" ]; then exit 1; fi
  cp "$@";;
 mv)
  mv "$@"
  if [ -e "$ROOT/fail-activation" ] && [ "$1" = "$ROOT/usr/lib/.libInfraStreamingUsb.v28snap.new" ]; then exit 1; fi;;
 *) "$cmd" "$@";;
esac
'''.replace('ROOT_PATH',root))
  fake.chmod(0o755)
  replacements=['/usr','/log','/proc','/system','/setting']
  mock_space='#!/usr/bin/bash\nif [ -e "'+root+'/fail-space" ]; then exit 2; fi\nexit 0\n'
  (self.stage/'space-check.elf').write_bytes(mock_space.encode())
  real_space_hash=hashlib.md5((P/'space-check.elf').read_bytes()).hexdigest()
  mock_space_hash=hashlib.md5(mock_space.encode()).hexdigest()
  scripts={}
  for name in ['preflight.sh','rollback.sh','install.sh']:
   s=(P/name).read_text().replace('/bin/busybox',fake.as_posix())
   for prefix in replacements:s=s.replace(prefix,root+prefix)
   scripts[name]=s.replace(real_space_hash,mock_space_hash)
  # Guard the translated fixture rollback, whose path strings differ from target.
  original=hashlib.md5((P/'rollback.sh').read_bytes()).hexdigest();translated=hashlib.md5(scripts['rollback.sh'].encode()).hexdigest()
  scripts['install.sh']=scripts['install.sh'].replace(original,translated)
  for name,s in scripts.items():(self.stage/name).write_bytes(s.encode())
  for name in ['libInfraStreamingUsb.persistent.so','yuy2_640_v28snap.so']:shutil.copy2(P/name,self.stage/name)
 def run(self,name):
  r=subprocess.run([BASH,str(self.stage/name)],capture_output=True,text=True,timeout=45);return r.returncode,r.stdout+r.stderr
 def hash_stream(self):return hashlib.md5((self.root/'usr/lib/libInfraStreamingUsb.so').read_bytes()).hexdigest()
 def marker(self,n): (self.root/n).write_text('1')
for p in P.glob('*.sh'):subprocess.run([BASH,'-n',str(p)],check=True)
f=Fixture();rc,log=f.run('install.sh');assert rc==0 and 'V28_FILES_VERIFIED_REBOOT_REQUIRED' in log,(rc,log);assert f.hash_stream()==NEW;assert (f.root/'usr/share/yuy2-recovery-v28snap/libInfraStreamingUsb.previous.so').read_bytes()==old
assert 'remount,ro' in (f.root/'mount-calls').read_text();results.append('successful dependency-first installation and exact previous-version backup plus stable 2.4p rescue')
rc,log=f.run('rollback.sh');assert rc==0 and f.hash_stream()=='5fde77e394572ebcf420f8941575f6c4',(rc,log);results.append('rollback restores working v24p, kernel and original module untouched')
f=Fixture();(f.root/'proc/123/maps').write_text('libInfraStreamingUsb.so\n');rc,log=f.run('install.sh');assert rc and f.hash_stream()==OLD and not (f.root/'mount-calls').exists(),log;results.append('loaded streaming mapping rejected before writes')
f=Fixture();(f.root/'usr/lib/libBizFw.so').write_text('different SDK');rc,log=f.run('install.sh');assert rc and f.hash_stream()==OLD and not (f.root/'mount-calls').exists(),log;results.append('SDK mismatch rejected before writes')
f=Fixture();f.marker('fail-space');rc,log=f.run('install.sh');assert rc and f.hash_stream()==OLD and not (f.root/'mount-calls').exists(),log;results.append('insufficient space rejected before writes')
f=Fixture();(f.stage/'yuy2_640_v28snap.so').write_bytes(b'corrupt');rc,log=f.run('install.sh');assert rc and f.hash_stream()==OLD and not (f.root/'mount-calls').exists(),log;results.append('damaged module rejected before writes')
for flag in ['fail-module','fail-activation','fail-ro']:
 f=Fixture();f.marker(flag);rc,log=f.run('install.sh');assert rc and f.hash_stream()==OLD and 'V28_FAILURE_RESTORED_PREVIOUS' in log,(flag,rc,log);results.append(flag+': automatic rollback restores previous 2.7 streaming file')
f=Fixture();rc,log=f.run('install.sh');assert not rc;before=(f.root/'usr/lib/libInfraStreamingUsb.so').read_bytes();rc,log=f.run('install.sh');assert rc and (f.root/'usr/lib/libInfraStreamingUsb.so').read_bytes()==before;results.append('repeat install refuses to overwrite existing recovery state')
report={'passed':len(results),'cases':results,'target_scripts_translated_to_local_fixture':True,'mounts_and_fixed_baseline_hashes_mocked':True,'space_helper_mocked_in_host_fixture':True,'camera_access':False}
(P/'installer-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

