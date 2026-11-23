from pathlib import Path
import sys,json
sys.path.insert(0,str(Path('.local/work/yc-frame-contract-20261029').resolve()));sys.path.insert(0,str(Path('.local/work/yc-subsystem-offline-20261029').resolve()))
from rtos import *
from thumb_xrefs import direct_calls
rows=[];o=Path('.local/outputs/sensor-bayer-20261030/followup')
for pc,target in direct_calls(DATA,BASE):
 if target in [0x635df178,0x635df194]:
  rows.append(dict(call=hex(pc),context=disasm(pc-24,pc+8)))
(o/'event-set-all-callers.json').write_text(json.dumps(rows,indent=2));print('event setter candidates',len(rows))
for r in rows:
 if '#0x2000' in r['context'] or '#0x100000' in r['context']:print(r['context'])
