"""Execute the actual three-file install/rollback scripts on an isolated fixture."""
from pathlib import Path
import tempfile,subprocess,hashlib,json,shutil,runpy
g=runpy.run_path(str(Path(__file__).with_name('package.py')));P=g['P'];O=g['O'];ROOT=g['ROOT'];STATIC=g['STATIC']
BASH='C:/msys64/usr/bin/bash.exe';md=lambda p:hashlib.md5(p.read_bytes()).hexdigest()
old=(ROOT/'.local/outputs/vga-v37/build/libInfraStreamingUsb.so').read_bytes()
kernel=(ROOT/'.local/outputs/vga-v37/usbg_video.ko').read_bytes()
assert hashlib.md5(old).hexdigest()==g['OLD'] and hashlib.md5(kernel).hexdigest()==g['OK']
class Fixture:
 def __init__(self):
  self.root=Path(tempfile.mkdtemp(prefix='installer-',dir=O));self.stage=self.root/'log/yuy2_640_v38vga';self.stage.mkdir(parents=True)
  for p,h in STATIC.items():
   f=self.root/p.lstrip('/');f.parent.mkdir(parents=True,exist_ok=True);f.write_text(h)
  (self.root/'usr/share/yuy2-recovery-v29full/libInfraStreamingUsb.v24p.so').write_bytes((ROOT/'.local/outputs/yuy2-640-v24p/candidate/libInfraStreamingUsb.persistent.so').read_bytes())
  (self.root/'usr/kmod/usbg_video.ko').write_bytes(kernel)
  (self.root/'usr/share/yuy2-recovery-v37vga/usbg_video.previous.ko').write_bytes((ROOT/'.local/outputs/yuy2-640-v24p/candidate/usbg_video.ko').read_bytes())
  (self.root/'usr/lib/libInfraStreamingUsb.so').write_bytes(old)
  for p,s in [('proc/123/maps','libBizFw.so\n'),('proc/mounts',''),('proc/uptime','123.00 0.00\n')]:
   f=self.root/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(s)
  r=self.root.as_posix();fake=self.root/'busybox'
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
 md5sum)
  for f in "$@"; do
   if [ -f "$f" ] && [ "$(wc -c < "$f")" = 32 ] && [[ "$(cat "$f")" =~ ^[0-9a-f]{32}$ ]]; then printf '%s  %s\\n' "$(cat "$f")" "$f"; else md5sum "$f"; fi
  done;;
 cp)
  if [ -e "$ROOT/fail-module" ] && [ "$2" = "$ROOT/usr/lib/.yuy2_v38vga.new" ]; then exit 1; fi
  if [ -e "$ROOT/fail-kernel" ] && [ "$2" = "$ROOT/usr/kmod/.usbg_video.v38vga.new" ]; then exit 1; fi
  cp "$@";;
 mv)
  mv "$@"
  if [ -e "$ROOT/fail-activation" ] && [ "$1" = "$ROOT/usr/lib/.libInfraStreamingUsb.v38vga.new" ]; then exit 1; fi
  if [ -e "$ROOT/fail-kernel-activation" ] && [ "$1" = "$ROOT/usr/kmod/.usbg_video.v38vga.new" ]; then exit 1; fi;;
 *) "$cmd" "$@";;
esac
'''.replace('ROOT_PATH',r))
  mockspace='#!/usr/bin/bash\n[ ! -e "'+r+'/fail-space" ]\n';(self.stage/'space-check.elf').write_bytes(mockspace.encode())
  scripts={}
  for n in ['preflight.sh','rollback.sh','install.sh']:
   s=(P/n).read_text().replace('/bin/busybox',fake.as_posix())
   # Replace only target path tokens. The fixture fake path already contains /log?
   for pre in ['/usr','/log','/proc','/system','/setting']:s=s.replace(pre,r+pre)
   s=s.replace('/lib/libpthread.so.0',r+'/lib/libpthread.so.0')
   scripts[n]=s.replace(md(P/'space-check.elf'),hashlib.md5(mockspace.encode()).hexdigest())
  scripts['install.sh']=scripts['install.sh'].replace(md(P/'rollback.sh'),hashlib.md5(scripts['rollback.sh'].encode()).hexdigest())
  for n,s in scripts.items():(self.stage/n).write_bytes(s.encode())
  for n in ['yuy2_640_v38vga.so','libInfraStreamingUsb.persistent.so','usbg_video.ko']:shutil.copyfile(P/n,self.stage/n)
 def run(self,n,*args):
  q=subprocess.run([BASH,str(self.stage/n),*args],capture_output=True,text=True,timeout=60);return q.returncode,q.stdout+q.stderr
 def marker(self,n):(self.root/n).write_text('1')
 def pair(self):return md(self.root/'usr/lib/libInfraStreamingUsb.so'),md(self.root/'usr/kmod/usbg_video.ko')
results=[]
for p in P.glob('*.sh'):subprocess.run([BASH,'-n',str(p)],check=True)
f=Fixture();rc,log=f.run('install.sh');assert rc==0 and 'V38_FILES_VERIFIED_REBOOT_REQUIRED' in log,(rc,log)
assert f.pair()==(g['NW'],g['NK']);b=f.root/'usr/share/yuy2-recovery-v38vga'
assert (b/'libInfraStreamingUsb.previous.so').read_bytes()==old and (b/'usbg_video.previous.ko').read_bytes()==kernel
results.append('success_exact_wrapper_and_kernel_backups_dependency_first_three_file_install')
rc,log=f.run('rollback.sh');assert rc==0 and f.pair()==(g['OLD'],g['OK']),(rc,log);results.append('default_rollback_restores_both_previous_files')
rc,log=f.run('rollback.sh','--bars');assert rc==0 and f.pair()==(g['STABLE'],g['KSTABLE']),(rc,log);results.append('bars_rollback_restores_stable_wrapper_and_original_kernel')
for case in ['loaded','sdk','space','corrupt-module','corrupt-kernel','repeat']:
 f=Fixture()
 if case=='loaded':(f.root/'proc/123/maps').write_text('libInfraStreamingUsb.so\n')
 elif case=='sdk':(f.root/'usr/lib/libBizFw.so').write_text('mismatch')
 elif case=='space':f.marker('fail-space')
 elif case=='repeat':(f.root/'usr/lib/yuy2_640_v38vga.so').write_text('already present')
 else:(f.stage/('usbg_video.ko' if case.endswith('kernel') else 'yuy2_640_v38vga.so')).write_text('corrupt')
 rc,log=f.run('install.sh');assert rc and f.pair()==(g['OLD'],g['OK']) and not (f.root/'mount-calls').exists(),(case,rc,log)
 results.append(case+'_rejected_before_remount')
for flag in ['fail-module','fail-kernel','fail-kernel-activation','fail-activation','fail-ro']:
 f=Fixture();f.marker(flag);rc,log=f.run('install.sh')
 assert rc and f.pair()==(g['OLD'],g['OK']) and 'V38_FAILURE_RESTORED_PAIR' in log,(flag,rc,log)
 assert 'remount,ro' in (f.root/'mount-calls').read_text();results.append(flag+'_restores_both_files_and_attempts_read_only')
out=dict(camera_access=False,actual_shell_scripts_executed=True,passed=results,limitations=['Busybox, mount, process listing and space helper mocked; no power-loss or hardware-filesystem emulation.','Firmware binary payloads copied and hash verified locally.'])
(O/'installer-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
