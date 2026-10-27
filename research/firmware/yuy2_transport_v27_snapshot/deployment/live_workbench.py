"""Keep one authenticated service session for sequential, recorded prototype jobs."""
from pathlib import Path
import io,json,re,sys,time,traceback
REPO=Path(r'D:\02_Development_And_Projects\pmca-re')
sys.path[:0]=[str(REPO/'research/common'),str(REPO)]
import senser_fix
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend
JOBS=Path('work/native-dmm-callback/live-jobs'); OUT=Path('outputs/native-dmm-callback/deployment/live')
JOBS.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
entered=False
def complete(dev):
 global entered
 entered=True
 SenserPlatformBackend(dev).start(); raw=dev.dev
 dev.setTerminalEnable(False);dev.setTerminalEnable(True)
 def drain(seconds,marker=None):
  buf=bytearray();end=time.monotonic()+seconds
  while time.monotonic()<end:
   b=raw.readTerminal()
   if b:
    buf.extend(b)
    if marker and re.search(rb'^'+marker.encode()+rb'$',buf.replace(b'\r',b''),re.M):break
   else:time.sleep(.02)
  return buf.decode('latin1').replace('\r','')
 try:
  drain(1);print('WORKBENCH_READY',flush=True)
  end=time.monotonic()+3600
  while time.monotonic()<end:
   for p in sorted(JOBS.glob('*.json')):
    result=OUT/(p.stem+'.result.json')
    if result.exists():continue
    job=json.loads(p.read_text(encoding='utf-8-sig'));ret={'id':p.stem}
    if job.get('close'):
     result.write_text(json.dumps({'closed':True}));print('WORKBENCH_CLOSED',flush=True);return
    try:
     for local,remote in job.get('uploads',[]):
      if not (remote.startswith('/log/yuy2_640_v27snap/') or remote.startswith('/tmp/v27-')):raise ValueError('upload outside prototype folder')
      dev.writeFile(remote,Path(local).read_bytes());print('UPLOADED',remote,flush=True)
     if 'terminal_lines' in job:
      log=''
      for command in job['terminal_lines']:
       raw.writeTerminal((command+'\n').encode('ascii'))
       log+=drain(1)
      marker='V27_DIRECT_'+p.stem
      raw.writeTerminal(('echo '+marker+'\n').encode('ascii'))
      log+=drain(8,marker)
      (OUT/(p.stem+'.log')).write_text(log,encoding='latin1');print(log[-16000:],flush=True)
      if not re.search(r'^'+marker+r'$',log,re.M):raise RuntimeError('Direct terminal marker missing')
     if 'shell' in job:
      remote='/tmp/v27-live-workbench.sh';dev.writeFile(remote,job['shell'].encode('ascii'))
      marker='YUY2_JOB_DONE_'+p.stem
      raw.writeTerminal(f'/bin/busybox sh {remote}; echo {marker}\n'.encode())
      log=drain(job.get('timeout',45),marker)
      (OUT/(p.stem+'.log')).write_text(log,encoding='latin1')
      ret['shell_completed']=bool(re.search(r'^'+marker+r'$',log,re.M))
      print(log[-16000:],flush=True)
      if job.get('expected_marker') and job['expected_marker'] not in log:raise RuntimeError('Required success marker absent')
     for remote,local in job.get('downloads',[]):
      b=io.BytesIO();dev.readFile(remote,b);Path(local).parent.mkdir(parents=True,exist_ok=True);Path(local).write_bytes(b.getvalue())
      print('DOWNLOADED',remote,len(b.getvalue()),flush=True)
     ret['ok']=True
    except Exception as e:
     ret.update(ok=False,error=repr(e));traceback.print_exc()
    result.write_text(json.dumps(ret,indent=2)+'\n');print('JOB_RESULT',json.dumps(ret),flush=True)
   time.sleep(.2)
 finally:
  try:dev.setTerminalEnable(False)
  except Exception:pass
senserShellCommand(complete=complete)
if not entered:raise SystemExit('No camera connected')
