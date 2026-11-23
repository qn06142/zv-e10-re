"""Compile and execute hardware-boundary fixtures locally; no camera access."""
from pathlib import Path
import argparse,json,subprocess
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=Path('.local/outputs/vga-v34'));a=ap.parse_args()
r=Path(__file__).parent/'recipe';a.output.mkdir(parents=True,exist_ok=True);exe=a.output/'test_vga_worker.exe'
subprocess.run(['C:/msys64/ucrt64/bin/gcc.exe','-O2','-fno-builtin','-DRAW_FRAME_CONVERSION_ONLY','-I'+str(r),str(r/'test_vga_worker.c'),str(r/'vga_contract.c'),str(r/'sony_yc_sds.c'),str(r/'sony_yc_metadata.c'),'-o',str(exe)],check=True)
names=['owned metadata publication','no SSYC','SDF error','output compression changed','undersized destination','ambiguous pixel Open','producer descriptor changed','MMIO pixel address','staging overlap','metadata Share transport error','metadata Share negative reply and exact reply words','metadata Open negative reply','metadata Open unsupported address site','metadata invalid physical span','metadata mmap failure','metadata stream-device open failure','metadata USB overlap','exact source rejection safely skipped','rejected first candidate then successful second candidate','wrong reply queue quarantined','wrong reply handle quarantined','wrong reply command quarantined','wrong reply type quarantined','transport error with negative-looking reply quarantined','unknown native error quarantined','unexpected reply addresses quarantined','stale pixel handle safely skipped with metadata cleanup','stale pixel on first candidate then successful second candidate']
rows=[]
for i,n in enumerate(names):
 p=subprocess.run([str(exe.resolve()),str(i)],capture_output=True,text=True,check=True)
 rows.append(dict(case=i,name=n,result=p.stdout.strip()))
report=dict(passed=len(rows),camera_access=False,hardware_boundaries_mocked=True,cases=rows)
(a.output/'worker-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
