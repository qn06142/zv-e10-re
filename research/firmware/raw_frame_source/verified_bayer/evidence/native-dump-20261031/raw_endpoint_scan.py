from pathlib import Path
import struct,json
r=Path('D:/02_Development_And_Projects/pmca-re/.local/dumps/camera_2025/usr/usr');rows=[]
for folder in ['lib','bin']:
 for p in (r/folder).iterdir():
  if not p.is_file():continue
  b=p.read_bytes();i=b.find(struct.pack('<I',0x12802f1))
  if i>=0:rows.append(dict(file=str(p),offset=hex(i)))
Path('.local/outputs/sensor-bayer-20261031/linux-endpoint-matches.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2))
