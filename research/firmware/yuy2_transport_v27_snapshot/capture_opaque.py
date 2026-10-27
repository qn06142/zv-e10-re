"""Capture advertised YUY2 packets unchanged; split opaque bytes for later analysis."""
from pathlib import Path
import argparse,hashlib,json,subprocess

def save_frames(path,folder):
 data=path.read_bytes();size=640*480*2;frames=[]
 for i in range(len(data)//size):
  chunk=data[i*size:(i+1)*size];name=f'frame-{i:04d}.bin';(folder/name).write_bytes(chunk)
  frames.append({'file':name,'bytes':len(chunk),'sha256':hashlib.sha256(chunk).hexdigest()})
 return {'bytes':len(data),'frame_bytes':size,'complete_frames':len(frames),'trailing_bytes':len(data)%size,'frames':frames,'source_pixel_format':'UNKNOWN; YUY2 is transport framing only','conversion_performed':False}

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
 ap.add_argument('--ffmpeg',default=r'C:\WINDOWS\ffmpeg.exe');ap.add_argument('--device',default='ZV-E10');ap.add_argument('--frames',type=int,default=10)
 ap.add_argument('--timeout',type=int,default=30);ap.add_argument('--dry-run',action='store_true');ap.add_argument('--existing',type=Path)
 args=ap.parse_args()
 if args.frames<1 or args.timeout<1:ap.error('frames and timeout must be positive')
 raw=args.output/'capture.bin'
 cmd=[args.ffmpeg,'-hide_banner','-nostdin','-f','dshow','-pixel_format','yuyv422','-video_size','640x480','-framerate','10','-rtbufsize','8M','-i','video='+args.device,'-map','0:v:0','-frames:v',str(args.frames),'-an','-c:v','copy','-f','rawvideo','-n',str(raw)]
 if args.dry_run:print(json.dumps({'command':cmd,'conversion':False,'frame_bytes':614400},indent=2));return
 args.output.mkdir(parents=True,exist_ok=False)
 if args.existing:
  raw.write_bytes(args.existing.read_bytes());code=None;log=b'Offline split of an existing opaque capture; no camera access.\n'
 else:
  try:
   r=subprocess.run(cmd,capture_output=True,timeout=args.timeout);code=r.returncode;log=r.stdout+r.stderr
  except subprocess.TimeoutExpired as e:code=124;log=(e.stdout or b'')+(e.stderr or b'')+b'\nCAPTURE_TIMEOUT\n'
 (args.output/'ffmpeg.log').write_bytes(log)
 report=save_frames(raw,args.output) if raw.exists() else {'bytes':0,'complete_frames':0,'conversion_performed':False}
 report.update(exit_code=code,command=cmd if not args.existing else None,camera_access=not bool(args.existing))
 (args.output/'capture.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
