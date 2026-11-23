from pathlib import Path
import sys,json,re,struct,array
sys.path.insert(0,str(Path('.local/work/yc-frame-contract-20261029').resolve()))
from rtos import DATA,BASE,disasm
O=Path('.local/outputs/sensor-bayer-20261030');O.mkdir(exist_ok=True)
for n,lo,hi in [('dualrec-bayer-driver',0x63b32188,0x63b324e0)]:
 (O/(n+'.txt')).write_text(disasm(lo,hi))
rows=[]
for m in re.finditer(rb'[ -~]{6,}\x00',DATA):
 s=m.group()[:-1].decode()
 if any(t in s.lower() for t in ['bayer','stlraw','store_raw','set_rawb','raw_device','raw_output','raw bit','raw_bit','rawcompress']):rows.append(dict(address=hex(BASE+m.start()),text=s))
(O/'raw-strings.json').write_text(json.dumps(rows,indent=2))
print('raw string leads',len(rows))
print((O/'dualrec-bayer-driver.txt').read_text())
