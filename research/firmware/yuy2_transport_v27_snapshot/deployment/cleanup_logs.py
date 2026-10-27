"""Archive/hash-verify/clear only named diagnostic captures, in one service session."""
from pathlib import Path,PurePosixPath
import hashlib,io,json,re,sys,time
REPO=Path(r'D:/02_Development_And_Projects/pmca-re');OUT=Path('outputs/native-dmm-callback/deployment/log-cleanup-04')
assert not OUT.exists();OUT.mkdir(parents=True)
sys.path[:0]=[str(REPO/'research/common'),str(REPO)]
import senser_fix
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend
entered=False

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
 def execute(script,marker):
  nonlocal serial
  serial+=1;remote='/tmp/v27-log-cleanup.sh';dev.writeFile(remote,script.encode('ascii'));done=f'V27_CLEANUP_DONE_{serial}'
  raw.writeTerminal(f'/bin/busybox sh {remote}; RC=$?; echo {done} $RC\n'.encode())
  log=drain(40,done);(OUT/f'{serial:02d}-shell.log').write_text(log,encoding='latin1');print(log[-3000:],flush=True)
  assert re.search(r'^'+done+r' 0$',log,re.M) and re.search(r'^'+marker+r'$',log,re.M),'cleanup shell failed; inspect evidence'
 def download(remote):
  b=io.BytesIO();dev.readFile(remote,b);return b.getvalue()
 try:
  drain(1)
  execute('''set -e
BB=/bin/busybox
/usr/bin/ulogio.elf lstop 131 > /tmp/v27-old-logger-stop.txt 2>&1 || true
/usr/bin/ulogio.elf filter on 131 error
/usr/bin/ulogio.elf filter on 135 error
/usr/bin/ulogio.elf filter on 136 error
for D in /log/yuy2_640* /log/yc_* /log/video_tab_* /log/menu_crash_* /log/usb_debug_*; do
[ -d "$D" ] || continue
for F in "$D"/* "$D"/*/*; do
[ -f "$F" ] || continue
case "${F##*/}" in *.log|biz*.bin|debug*.bin|klog*.bin|trace*.bin|*ulogio*.txt) $BB md5sum "$F";; esac
done
done > /tmp/v27-cleanup-inventory.md5
echo V27_SPACE_CHECK_FOLLOWS_IN_PREFLIGHT
echo V27_CLEANUP_INVENTORY_READY
''','V27_CLEANUP_INVENTORY_READY')
  inventory=download('/tmp/v27-cleanup-inventory.md5');(OUT/'inventory.md5').write_bytes(inventory);entries=[]
  for line in inventory.decode('ascii').splitlines():
   m=re.fullmatch(r'([0-9a-f]{32})\s+(/log/[A-Za-z0-9_./-]+)',line);assert m,line
   md5,remote=m.groups();parts=PurePosixPath(remote).parts
   assert '..' not in parts and parts[2].startswith(('yuy2_640','yc_','video_tab_','menu_crash_','usb_debug_'))
   local=OUT/'archive'/PurePosixPath(remote).relative_to('/log');local.parent.mkdir(parents=True,exist_ok=True)
   data=download(remote);local.write_bytes(data);assert hashlib.md5(data).hexdigest()==md5,(remote,'archive mismatch; nothing deleted')
   entries.append({'path':remote,'md5':md5,'bytes':len(data)});print('ARCHIVED',remote,len(data),flush=True)
  (OUT/'verified-archive.json').write_text(json.dumps(entries,indent=2)+'\n')
  commands=['set -e','BB=/bin/busybox']
  for e in entries:commands.append(f'[ "$(/bin/busybox md5sum {e["path"]} | /bin/busybox cut -d " " -f 1)" = {e["md5"]} ]')
  for e in entries:commands.extend([f'/bin/busybox rm {e["path"]}',f'[ ! -e {e["path"]} ]'])
  commands.extend(['/bin/busybox sync','echo V27_VERIFIED_LOGS_CLEARED'])
  execute('\n'.join(commands)+'\n','V27_VERIFIED_LOGS_CLEARED')
  report={'files':len(entries),'bytes':sum(e['bytes'] for e in entries),'archive_verified':True,'deletions_confirmed':True}
  (OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
 finally:
  try:dev.setTerminalEnable(False)
  except Exception:pass
senserShellCommand(complete=complete)
if not entered:raise SystemExit('No camera connected; cleanup did not run')


