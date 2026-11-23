"""Bounded host-receipt benchmark. Writes only first raw frame, per-frame hashes/times and FFmpeg log."""
from pathlib import Path
import argparse,subprocess,time,threading,json,hashlib
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--seconds',type=float,default=8);ap.add_argument('--ffmpeg',default='C:/WINDOWS/ffmpeg.exe');a=ap.parse_args()
assert 1<=a.seconds<=15
assert not a.output.exists(),'Preserve previous benchmark'
a.output.mkdir(parents=True)
cmd=[a.ffmpeg,'-hide_banner','-nostdin','-f','dshow','-video_size','640x480','-framerate','60','-pixel_format','yuyv422','-i','video=ZV-E10','-an','-c:v','copy','-t',str(a.seconds),'-f','rawvideo','pipe:1']
rows=[];buf=bytearray();start=time.monotonic();killed=[]
with (a.output/'ffmpeg.log').open('wb') as log:
 p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=log)
 def expire():
  if p.poll() is None:killed.append(True);p.kill()
 timer=threading.Timer(a.seconds+5,expire);timer.start()
 try:
  while True:
   b=p.stdout.read(65536)
   if not b:break
   now=time.monotonic()-start;buf.extend(b)
   while len(buf)>=614400:
    frame=bytes(buf[:614400]);del buf[:614400]
    if not rows:(a.output/'first-frame.yuy2').write_bytes(frame)
    rows.append({'frame':len(rows)+1,'receipt_seconds':now,'sha256':hashlib.sha256(frame).hexdigest()})
  rc=p.wait(timeout=3)
 finally:
  timer.cancel()
  if p.poll() is None:p.kill();p.wait()
span=rows[-1]['receipt_seconds']-rows[0]['receipt_seconds'] if len(rows)>1 else 0
out={'command':cmd,'returncode':rc,'watchdog_killed':bool(killed),'wall_seconds':time.monotonic()-start,'frames':len(rows),'trailing_bytes':len(buf),'receipt_fps_excluding_initial_open':(len(rows)-1)/span if span else None,'unique_payload_hashes':len({r['sha256'] for r in rows}),'limitations':['Host receipt cadence, not sensor exposure fps.','Hashes do not alone prove scene freshness.','60fps is a request ceiling, not a promised rate.']}
(a.output/'frames.json').write_text(json.dumps(rows,indent=2));(a.output/'summary.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
