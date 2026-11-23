"""Offline execution of original metadata-to-processing parameter block; no camera access."""
from pathlib import Path
import sys,struct,json
sys.path.insert(0,'.local/work/yc-frame-contract-20261029')
from rtos_harness import *
h=Harness();u=h.u;meta=MEM+0x10000;out=MEM+0x20000
# Stop before caller-dependent processing dispatch. Original block only copies fields.
h.callbacks[0x6368c976]=lambda a:u.reg_write(UC_ARM_REG_PC,STOP)
reference=bytearray(Path('.local/outputs/vga-v33/capture-first-01/logs/source-ssyc-retained.bin').read_bytes()[64:124])
rows=[]
for depth in [0,1,2,3,4,8,10,12,255]:
 for compression in [0,1,2,3,255]:
  b=bytearray(reference);b[54]=depth;b[47]=compression
  u.mem_write(meta,bytes(b));u.mem_write(out,bytes([165])*128)
  h.run(0x6368c924,0,meta,0,out,balanced=False)
  result=bytes(u.mem_read(out,32));mode=struct.unpack_from('<I',result,20)[0];comp=struct.unpack_from('<I',result,24)[0]
  assert mode==(0 if depth==0 else 1)
  assert comp==(compression if compression in [1,2,3] else 0)
  assert struct.unpack_from('<HH',result)==(1920,1080)
  rows.append({'input_YC_byte36':depth,'input_YC_compression':compression,'processing_word14':mode,'processing_word18':comp})
report={'original_block':['0x6368c924','0x6368c976'],'camera_access':False,'original_instructions_executed':True,'cases':rows,'conclusion':'Native YC metadata byte0x36 is consumed as zero versus nonzero for this processing word. This is not the codec 0/1/2/3 bit-depth enum proof and does not configure or generate actual high-precision pixels.','hardware_services':'Not invoked; stopped before processing dispatch.'}
Path('.local/outputs/yc-high-depth-20261030/yc-processing-depth-control.json').write_text(json.dumps(report,indent=2));print('Passed',len(rows),'native metadata-to-processing cases')
