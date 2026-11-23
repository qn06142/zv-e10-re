from pathlib import Path
import sys,io,re,json,time,hashlib
REPO=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(REPO/'research/common'),str(REPO)]
import senser_fix
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend
from zve10_dumpall import _preflight
import argparse
parser=argparse.ArgumentParser(description='Single-use guarded resident runtime v02 install; never sends GO')
parser.add_argument('--out',type=Path,required=True)
out=parser.parse_args().out
out.mkdir(parents=True,exist_ok=False)
journal={'mode':'senser','camera_writes':False,'commands':[]}
connected=False
log=(out/'terminal.txt').open('w',encoding='utf-8')
def complete(dev):
 global connected
 connected=True
 SenserPlatformBackend(dev).start()
 raw=dev.dev
 dev.setTerminalEnable(False);dev.setTerminalEnable(True)
 end=time.monotonic()+1
 while time.monotonic()<end:
  chunk=raw.readTerminal()
  if chunk:log.write(chunk.decode('latin1'))
  else:time.sleep(.02)
 def sh(command):
  tag='GUIREAD%03d'%len(journal['commands'])
  raw.writeTerminal((command+'\n').encode('ascii'))
  raw.writeTerminal(('echo '+tag+'=$?\n').encode('ascii'))
  data=b'';deadline=time.monotonic()+45
  while time.monotonic()<deadline:
   chunk=raw.readTerminal()
   if chunk:
    data+=chunk
    text=data.decode('latin1').replace('\r','')
    m=re.search(r'(?m)^'+tag+r'=(\d+)\s*$',text)
    if m:break
   else:time.sleep(.02)
  else:raise RuntimeError('Missing completion: '+command)
  log.write(text);log.flush()
  journal['commands'].append({'command':command,'rc':int(m.group(1)),'output':text})
  print(command,'rc='+m.group(1),flush=True)
  return text,int(m.group(1))
 def md5(path):
  text,rc=sh('busybox md5sum '+path)
  rows=re.findall(r'(?m)^([0-9a-f]{32})\s+'+re.escape(path)+r'\s*$',text)
  if rc or len(rows)!=1:raise RuntimeError('Checksum unavailable: '+path)
  return rows[0]
 def must(command):
  text,rc=sh(command)
  if rc:raise RuntimeError('Camera command failed: '+command)
  return text
 def pull(remote):
  before=md5(remote)
  buf=io.BytesIO();dev.readFile(remote,buf);data=buf.getvalue()
  if hashlib.md5(data).hexdigest()!=before or md5(remote)!=before:
   raise RuntimeError('Readback mismatch: '+remote)
  return data
 def upload(remote,data):
  dev.writeFile(remote,data)
  if pull(remote)!=data:raise RuntimeError('Uploaded bytes differ: '+remote)
 try:
  must('busybox cat /proc/uptime /proc/sys/kernel/random/boot_id /sys/devices/system/cpu/online')
  mounts=must('busybox cat /proc/mounts')
  assert re.search(r'(?m)^\S+ /usr ext2 ro(?:,|\s)',mounts),'Expected /usr read-only'
  before=md5('/system/av-cam.bin');assert before=='90096db2c76148f4f9db5d104e5c608c'
  assert md5('/usr/lib/viewUnified6.so')=='9a3cc1f700cbe4a255e29cb5d5b2e2fc'
  assert hashlib.sha256(pull('/log/zve10-ram-loader/payload.bin')).hexdigest()=='9f4cccc252779e7d752fe5680b8c9e0f8624868257c3c4a3aabb3d1ca5a348ce'
  modules=must('busybox cat /proc/modules')
  assert not re.search(r'(?m)^zve10_(?:ram_boot|boot_bridge) ',modules),'Test module already loaded'
  old=pull('/log/zve10-ram-boot/boot.ko')
  assert hashlib.sha256(old).hexdigest()=='87d5ee9955cfe1229376b8cc36b804de11b8c6aacdeae14612ac5432d53235ad'
  candidate=(REPO/'.local/out/zve10-ram-runtime-v02/zve10_ram_boot.ko').read_bytes()
  assert hashlib.sha256(candidate).hexdigest()=='279bc0718128b8dc832163314e4e360582ecf272642f68a679aa6ba0a684038a'
  destination='/log/zve10-ram-boot/runtime-v02'
  must('test ! -e '+destination)
  journal['camera_writes']=True
  must('busybox mkdir '+destination)
  upload(destination+'/previous-reset.ko',old)
  upload(destination+'/resident.next.ko',candidate)
  loaded=False
  try:
   must('busybox insmod '+destination+'/resident.next.ko');loaded=True
   state=must('busybox cat /sys/module/zve10_ram_boot/parameters/state')
   assert re.search(r'(?m)^READY\s*$',state),'Stage not READY'
   journal['stage_state']='READY; GO not sent'
   must("busybox dmesg | busybox grep 'ZVBOOT_STAGE'")
  finally:
   if loaded:must('busybox rmmod zve10_ram_boot')
  assert not re.search(r'(?m)^zve10_ram_boot ',must('busybox cat /proc/modules'))
  assert pull(destination+'/previous-reset.ko')==old
  assert pull('/log/zve10-ram-boot/boot.ko')==old
  must('busybox mv '+destination+'/resident.next.ko /log/zve10-ram-boot/boot.ko')
  must('busybox sync')
  assert pull('/log/zve10-ram-boot/boot.ko')==candidate
  assert md5('/system/av-cam.bin')==before
  assert md5('/usr/lib/viewUnified6.so')=='9a3cc1f700cbe4a255e29cb5d5b2e2fc'
  assert re.search(r'(?m)^\S+ /usr ext2 ro(?:,|\s)',must('busybox cat /proc/mounts'))
  journal.update({'installed':True,'module_sha256':hashlib.sha256(candidate).hexdigest(),'bytes':len(candidate),'full_readback_match':True,'go_sent':False,'module_loaded_at_close':False,'status':'resident-runtime-installed-activation-pending'})
  print('RESIDENT_RUNTIME_INSTALLED_VERIFIED_NO_GO_SENT',flush=True)

 finally:
  dev.setTerminalEnable(False)
try:
 _preflight();senserShellCommand(complete=complete)
 if not connected:raise RuntimeError('No authenticated session')
finally:
 (out/'session.json').write_text(json.dumps(journal,indent=2)+'\n')
 log.close()
