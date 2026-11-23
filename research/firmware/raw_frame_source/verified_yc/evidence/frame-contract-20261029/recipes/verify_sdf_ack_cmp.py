"""Original SDK send/ACK/CMP control flow with controlled receiver results."""
from pathlib import Path
import io,struct,json
from elftools.elf.elffile import ELFFile
from unicorn import *
from unicorn.arm_const import *
P=Path('D:/02_Development_And_Projects/pmca-re/.local/dumps/camera_2025/usr/usr/lib/libBizFw.so')
e=ELFFile(io.BytesIO(P.read_bytes()));B=0x10000000;M=0x40000000;ST=0x50010000;STOP=0x60000000
cases=[]
for ack_status,cmp_status in [(0,0),(5,0),(0,7)]:
 u=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
 loads=[s for s in e.iter_segments() if s['p_type']=='PT_LOAD'];end=max(s['p_vaddr']+s['p_memsz'] for s in loads)
 u.mem_map(B,(end+4095)&~4095)
 for s in loads:u.mem_write(B+s['p_vaddr'],s.data())
 for a,n in [(M,0x10000),(ST,0x10000),(STOP,0x1000)]:u.mem_map(a,n)
 def put(a,v):u.mem_write(a,struct.pack('<I',v&0xffffffff))
 obj=M;cmp=M+0x1000;ack=M+0x2000;cmd=M+0x3000;events=[]
 put(obj+4,0x12345678);put(ack+8,ack_status);put(cmp+8,cmp_status)
 u.reg_write(UC_ARM_REG_SP,ST+0x8000);u.reg_write(UC_ARM_REG_LR,STOP|1)
 for reg,v in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],[obj,cmp,24,ack]):u.reg_write(reg,v)
 for i,v in enumerate([16,cmd,68]):put(ST+0x8000+i*4,v)
 def hook(u,pc,size,_):
  if pc-B not in [0x2bd30,0x2c280,0x2b004,0x2cbc4,0x2add4]:return
  a=[u.reg_read(r) for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]]
  if pc-B in [0x2bd30,0x2c280]:
   fifth=struct.unpack('<I',u.mem_read(u.reg_read(UC_ARM_REG_SP),4))[0]
   events.append(dict(call='send' if pc-B==0x2bd30 else 'receive',pointer=hex(a[1]),bytes=a[2],queue=hex(a[3]),fifth=hex(fifth)))
  u.reg_write(UC_ARM_REG_R0,0);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 u.hook_add(UC_HOOK_CODE,hook);u.emu_start(B+0x366f1,STOP,count=2000)
 assert u.reg_read(UC_ARM_REG_PC)==STOP and u.reg_read(UC_ARM_REG_R0)==0
 assert [v['bytes'] for v in events]==([68,16] if ack_status else [68,16,24])
 assert all(v['fifth']=='0xffffffff' for v in events if v['call']=='receive')
 cases.append(dict(ack_payload_status=ack_status,cmp_payload_status=cmp_status,sdk_return=0,events=events))
out=dict(camera_access=False,original_sdk_function='libBizFw.so+0x366f0',cases=cases,mocked=['Send, receive, logging PLT targets; payloads supplied by fixture'],conclusion='SDK return 0 alone is insufficient: ACK rejection and nonzero CMP payload status can both return 0. Check ACK and CMP payloads. Receives use infinite timeout.')
Path('.local/outputs/yc-frame-contract-20261029/sdf-ack-cmp-control-flow.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
