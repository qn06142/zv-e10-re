"""One explicit service job. No polling queue, automatic retry, install or reboot chain."""
from pathlib import Path
import argparse,hashlib,io,json,re,sys,time
ap=argparse.ArgumentParser();ap.add_argument('step',choices=['preflight','stage','install','readback','rollback']);ap.add_argument('--package',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--repo',type=Path,default=Path(r'D:/02_Development_And_Projects/pmca-re'));a=ap.parse_args()
pack=a.package.resolve();manifest=json.loads((pack/'package-manifest.json').read_text());out=a.output.resolve()
if out.exists():raise SystemExit('Use a fresh evidence directory')
expected={'preflight.sh','rollback.sh','install.sh','yuy2_640_v27snap.so','libInfraStreamingUsb.persistent.so','space-check.elf'}
assert set(manifest['files'])==expected
for name,info in manifest['files'].items():
 data=(pack/name).read_bytes();assert hashlib.sha256(data).hexdigest()==info['sha256'] and len(data)==info['bytes'],name
out.mkdir(parents=True);sys.path[:0]=[str(a.repo/'research/common'),str(a.repo)]
import senser_fix
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend
D='/log/yuy2_640_v27snap';entered=False;result={'step':a.step,'ok':False,'no_automatic_retry':True}
def complete(dev):
 global entered
 entered=True;SenserPlatformBackend(dev).start();raw=dev.dev;dev.setTerminalEnable(False);dev.setTerminalEnable(True)
 def drain(seconds,done=None):
  data=bytearray();end=time.monotonic()+seconds
  while time.monotonic()<end:
   b=raw.readTerminal()
   if b:
    data.extend(b)
    if done and re.search(rb'^'+done.encode()+rb' [0-9]+\r?$',data,re.M):break
   else:time.sleep(.02)
  return data.decode('latin1').replace('\r','')
 serial=0
 def execute(script,marker,timeout=55):
  nonlocal serial
  serial+=1;remote=D+'/explicit-job.sh';dev.writeFile(remote,script.encode('ascii'))
  done='V27_EXPLICIT_JOB_DONE_'+str(serial)
  raw.writeTerminal(f'/bin/busybox sh {remote}; RC=$?; echo {done} $RC\n'.encode('ascii'))
  log=drain(timeout,done);(out/f'{serial:02d}-terminal.log').write_text(log,encoding='latin1');print(log[-12000:],flush=True)
  match=re.search(r'^'+done+r' ([0-9]+)$',log,re.M)
  if not match or match[1]!='0' or not re.search(r'^'+re.escape(marker)+r'$',log,re.M):raise RuntimeError('Job did not return both exit zero and its success marker; inspect evidence, do not blindly retry')
 def verify_uploaded(name,remote):
  h=manifest['files'][name]['md5'];return f'[ "$(/bin/busybox md5sum {remote} | /bin/busybox cut -d " " -f 1)" = {h} ]\n'
 try:
  drain(1)
  raw.writeTerminal(f'/bin/busybox mkdir -p {D}\n'.encode('ascii'));drain(1)
  if a.step=='preflight':
   checks='set -e\n'
   for name in ['preflight.sh','space-check.elf']:
    remote=D+'/'+name;dev.writeFile(remote,(pack/name).read_bytes());checks+=verify_uploaded(name,remote)
   execute(checks+f'/bin/busybox sh {D}/preflight.sh\n','V27_PREFLIGHT_OK')
  elif a.step=='stage':
   execute(f'set -e\n[ -d {D} ]\necho V27_STAGE_DIRECTORY_READY\n','V27_STAGE_DIRECTORY_READY')
   for name in sorted(expected):dev.writeFile(D+'/'+name,(pack/name).read_bytes())
   execute('set -e\n'+''.join(verify_uploaded(n,D+'/'+n) for n in sorted(expected))+'echo V27_STAGE_HASHES_VERIFIED\n','V27_STAGE_HASHES_VERIFIED')
  elif a.step=='install':
   execute('set -e\n'+''.join(verify_uploaded(n,D+'/'+n) for n in sorted(expected))+f'/bin/busybox sh {D}/install.sh\n','V27_FILES_VERIFIED_REBOOT_REQUIRED')
   for remote,name,md5 in [('/usr/lib/libInfraStreamingUsb.so','stream-readback.so',manifest['files']['libInfraStreamingUsb.persistent.so']['md5']),('/usr/lib/yuy2_640_v27snap.so','module-readback.so',manifest['files']['yuy2_640_v27snap.so']['md5']),('/usr/share/yuy2-recovery-v27snap/libInfraStreamingUsb.v24p.so','v24p-backup-readback.so','5fde77e394572ebcf420f8941575f6c4')]:
    buf=io.BytesIO();dev.readFile(remote,buf);data=buf.getvalue();(out/name).write_bytes(data);assert hashlib.md5(data).hexdigest()==md5,(name,'readback mismatch')
  elif a.step=='rollback':
   remote='/usr/share/yuy2-recovery-v27snap/rollback.sh'
   execute('set -e\n'+verify_uploaded('rollback.sh',remote)+f'/bin/busybox sh {remote}\n','V27_ROLLED_BACK_TO_WORKING_V24P_REBOOT_REQUIRED')
  else:
   checks='set -e\n' 
   for remote,md5 in [('/usr/lib/libInfraStreamingUsb.so',manifest['files']['libInfraStreamingUsb.persistent.so']['md5']),('/usr/lib/yuy2_640_v27snap.so',manifest['files']['yuy2_640_v27snap.so']['md5']),('/usr/lib/yuy2_640_v24p.so','9181ef744955190d04728cf4ef7965c5'),('/usr/kmod/usbg_video.ko','c1cad400372e26eca729e4b9bc47a237')]:
    checks+=f'[ "$(/bin/busybox md5sum {remote} | /bin/busybox cut -d " " -f 1)" = {md5} ]\n'
   checks+='/bin/busybox cat /proc/uptime\n/bin/busybox cat /proc/$(/bin/busybox pidof im.elf)/maps\necho V27_READBACK_HASHES_OK\n'
   execute(checks,'V27_READBACK_HASHES_OK')
  result['ok']=True
 except Exception as e:result['error']=repr(e);raise
 finally:
  (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
  try:dev.setTerminalEnable(False)
  except Exception:pass
senserShellCommand(complete=complete)
if not entered:raise SystemExit('No camera connected; no job ran')
