"""Capture native VGA payload bytes unchanged. No camera/service operations."""
import argparse,json,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--ffmpeg',default='ffmpeg');p.add_argument('--device',default='ZV-E10')
p.add_argument('--output',type=Path,required=True);p.add_argument('--frames',type=int,default=5)
p.add_argument('--timeout',type=float,default=25)
a=p.parse_args()
if a.frames<1 or a.frames>100 or not 1<=a.timeout<=120:p.error('frames 1..100; timeout 1..120 seconds')
if a.output.exists():p.error('output already exists; preserve earlier captures')
a.output.parent.mkdir(parents=True,exist_ok=True)
command=[a.ffmpeg,'-hide_banner','-nostdin','-f','dshow','-video_size','640x480','-framerate','10',
         '-pixel_format','yuyv422','-i','video='+a.device,'-an','-c:v','copy','-frames:v',str(a.frames),
         '-f','rawvideo',str(a.output)]
start=time.monotonic();timeout=False
with a.output.with_suffix('.ffmpeg.log').open('wb') as log:
 proc=subprocess.Popen(command,stdout=log,stderr=log)
 try:rc=proc.wait(timeout=a.timeout)
 except subprocess.TimeoutExpired:timeout=True;proc.kill();rc=proc.wait(timeout=5)
n=a.output.stat().st_size if a.output.exists() else 0
report={'command':command,'returncode':rc,'timed_out':timeout,'seconds':time.monotonic()-start,
        'bytes':n,'complete_614400_byte_payloads':n//614400,'trailing_bytes':n%614400,
        'packing':'UNVERIFIED native VGA; YUY2 is the advertised envelope',
        'framing':'no ZVYC0029 header; do not use revision 2.9 reassembler'}
a.output.with_suffix('.capture.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
raise SystemExit(0 if not timeout and rc==0 and n==a.frames*614400 else 1)
