from pathlib import Path
import sys,struct,json
from capstone import *
sys.path.insert(0,str(Path('.local/work/yc-frame-contract-20261029').resolve()))
from rtos import *
c=Cs(CS_ARCH_ARM,CS_MODE_THUMB);rows=[]
for off in range(0,len(DATA)-3,2):
 a,b=struct.unpack_from('<HH',DATA,off)
 if a&0xf800!=0xf000 or b&0x8000==0:continue
 i=next(c.disasm(DATA[off:off+4],BASE+off),None)
 if i and i.size==4 and i.mnemonic in ['bl','b.w'] and i.op_str in ['#0x63d86f08','#0x63d86ee4']:
  rows.append(dict(address=hex(i.address),kind=i.mnemonic,context=disasm(i.address-24,i.address+8)))
p=Path('.local/outputs/sensor-bayer-20261030/followup/readout-signaller-branches.json');p.write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2))
