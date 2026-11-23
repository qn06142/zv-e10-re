"""Generate the private host fixture header from the verified 3.8 record; no camera access."""
from pathlib import Path
import hashlib,argparse
ap=argparse.ArgumentParser();ap.add_argument('record',type=Path);a=ap.parse_args()
b=a.record.read_bytes()
assert hashlib.sha256(b).hexdigest()=='20cde3d3c4d6529dc7ccb8300260029e21b171d2d56cece77b37e36bc9ebb539'
assert len(b)==8272 and b[:8]==b'YC38RJ01'
out=Path(__file__).parent/'recipe/test_rejected_fixture.h'
out.write_text('/* Private historical bytes; never replay on camera. */\nstatic const unsigned char rejected_fixture[4096]={'+','.join(str(v) for v in b[80:4176])+'};\n')
print(out)
