from pathlib import Path
import json,struct
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_HOOK_CODE
from unicorn.arm_const import *
import argparse
ap=argparse.ArgumentParser(description='Execute revision 2 Thumb loader success/failure cases')
ap.add_argument('--output',type=Path,required=True)
ap.add_argument('--stream-base',type=lambda v:int(v,0),default=0x0a73d000)
args=ap.parse_args()
O=args.output.resolve();SB=args.stream_base;DL=0x40ba000;STACK=0x60008000;STOP=0x50000000
rs=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]
def string(u,p):return bytes(u.mem_read(p,100)).split(b'\0')[0].decode()
results=[]
for failed in ['none','dlopen','dlsym','status']:
 u=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
 for a,n in [(SB,0x10000),(DL,0x10000),(STACK-0x8000,0x10000),(STOP,4096),(0x10000000,4096)]:u.mem_map(a,n)
 u.mem_write(SB+0x90c0,(O/'bootstrap-after.bin').read_bytes())
 calls=[]
 def hook(u,a,size,data):
  if a==(DL+0xbb0):
   assert string(u,u.reg_read(UC_ARM_REG_R0))=='/log/yuy2_640_v21/yuy2_640_v21.so'
   assert u.reg_read(UC_ARM_REG_R1)==0x102
   assert u.reg_read(UC_ARM_REG_SP)%8==0
   calls.append('dlopen');u.reg_write(UC_ARM_REG_R0,0 if failed=='dlopen' else 123);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
  elif a==DL+0xc48:
   assert string(u,u.reg_read(UC_ARM_REG_R1))=='yuy2_status'
   calls.append('dlsym');u.reg_write(UC_ARM_REG_R0,0 if failed=='dlsym' else 0x10000001);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
  elif a==0x10000000:
   calls.append('status');u.reg_write(UC_ARM_REG_R0,0 if failed=='status' else 1);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 u.hook_add(UC_HOOK_CODE,hook)
 vals=[0x71000000+i for i in range(12)]
 for r,v in zip(rs,vals):u.reg_write(r,v)
 u.reg_write(UC_ARM_REG_SP,STACK);u.reg_write(UC_ARM_REG_LR,STOP|1)
 target=SB+0x8d0c if failed=='none' else STOP
 u.emu_start((SB+0x90c0)|1,target,count=5000)
 assert u.reg_read(UC_ARM_REG_PC)==target,(failed,hex(u.reg_read(UC_ARM_REG_PC)),calls,hex(u.reg_read(UC_ARM_REG_R3)))
 if failed=='none':
  assert u.reg_read(UC_ARM_REG_SP)==STACK-24
  assert list(struct.unpack('<6I',u.mem_read(STACK-24,24)))==[vals[3],vals[4],vals[5],vals[6],vals[7],STOP|1]
  assert u.reg_read(UC_ARM_REG_R4)==vals[0] and u.reg_read(UC_ARM_REG_R0)==4
  assert u.reg_read(UC_ARM_REG_R1)==0 and u.reg_read(UC_ARM_REG_R2)==0
 else:
  assert u.reg_read(UC_ARM_REG_SP)==STACK and u.reg_read(UC_ARM_REG_R0)==4
  assert [u.reg_read(r) for r in rs[1:]]==vals[1:]
 results.append({'bootstrap_case':failed,'calls':calls})
(O/'bootstrap-verification.json').write_text(json.dumps(results,indent=2)+'\n')
print('Bootstrap cases passed:',len(results))
