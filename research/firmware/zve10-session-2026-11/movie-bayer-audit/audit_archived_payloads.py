"""Audit existing alleged RAW captures without accepting filenames as provenance."""
import argparse,json,hashlib
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('repo',type=Path);a=p.parse_args()
directory=a.repo/'captures/usb3_24fps_session'
summary=json.loads((directory/'session_summary.json').read_text())
files=[]
for f in sorted(directory.glob('*.raw')):
 d=f.read_bytes()
 files.append(dict(name=f.name,length=len(d),sha256=hashlib.sha256(d).hexdigest(),matches_mock_aa55=d==b'\xaa\x55'*(len(d)//2)))
assert len(files)==5 and all(f['matches_mock_aa55'] for f in files)
assert summary['total_frames']==0 and summary['success'] is False
print(json.dumps(dict(summary=summary,raw_files=files,valid_bayer_source_evidence=False,reason='Every RAW file exactly matches the receiver mock fill; the current summary records zero UVC frames.'),indent=2))
