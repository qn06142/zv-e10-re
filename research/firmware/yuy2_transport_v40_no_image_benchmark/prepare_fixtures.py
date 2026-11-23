from pathlib import Path
import hashlib
specs=[('.local/outputs/vga-v38/capture-first-01/logs/rejected-source.yc38','20cde3d3c4d6529dc7ccb8300260029e21b171d2d56cece77b37e36bc9ebb539','test_rejected_fixture.h','rejected_fixture'),('.local/outputs/vga-v39/capture-first-01/logs/rejected-source.yc38','e4ee15a700c0025e75c08dedede49441b426b3ba6f506ae05219180ba37574fb','test_no_image_fixture.h','no_image_fixture')]
for f,h,n,v in specs:
 b=Path(f).read_bytes();assert hashlib.sha256(b).hexdigest()==h
 (Path(__file__).parent/'recipe'/n).write_text('/* Private fixture, never replay live identities. */\nstatic const unsigned char '+v+'[4096]={'+','.join(str(x) for x in b[80:4176])+'};\n')
