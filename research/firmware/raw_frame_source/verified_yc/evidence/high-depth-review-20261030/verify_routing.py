"""Execute the cited pointer-routing block with controlled flag; no pixel/hardware operations."""
from pathlib import Path
import sys,struct,json
sys.path.insert(0,'.local/work/yc-frame-contract-20261029')
from rtos_harness import *
rows=[]
for flag in [0,1,2]:
 h=Harness();u=h.u;obj=MEM;out=MEM+0x20000;frame=MEM+0x30000;source=MEM+0x40000;pix=MEM+0x50000;calls=[]
 h.put(obj+0x4bb0,flag);h.put(obj+0x4bb4,32);h.put(frame+16,source)
 payload=struct.pack('<I',pix)+bytes(range(60));u.mem_write(source,payload);u.mem_write(out,bytes(256))
 def copy(a):
  calls.append({'operation':'copy','bytes':a[2]});u.mem_write(a[0],bytes(u.mem_read(a[1],a[2])));h.ret(a[0])
 def mapping(a):calls.append({'operation':'map_pointer','site_argument':a[1]});h.ret(a[0])
 h.callbacks[0x63daefea]=copy;h.callbacks[0x63c48e0c]=mapping;h.callbacks[0x639e9564]=lambda a:u.reg_write(UC_ARM_REG_PC,STOP)
 u.reg_write(UC_ARM_REG_R4,obj);u.reg_write(UC_ARM_REG_R5,out);u.reg_write(UC_ARM_REG_R6,frame)
 h.run(0x639e953a,balanced=False)
 if flag==1:
  assert calls==[{'operation':'copy','bytes':64},{'operation':'map_pointer','site_argument':17}]
  assert h.word(out+0x4c)==pix+32
 else:assert not calls
 rows.append({'field_obj_4bb0':flag,'calls':calls,'output_pointer':hex(h.word(out+0x4c))})
out={'camera_access':False,'original_branch_instructions_executed':True,'cases':rows,'mocked':['64-byte copy implementation','physical pointer mapping returns identity'],'conclusion':'Flag1 enables a 64-byte record copy and pointer mapping/offset adjustment; this block alone does not prove pixel-plane copy bypass, precision, or that this field is bit_depth.'}
Path('.local/outputs/yc-high-depth-review-20261030/routing-block-verification.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
