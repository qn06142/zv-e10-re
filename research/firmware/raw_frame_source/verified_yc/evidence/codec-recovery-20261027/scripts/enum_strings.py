from pathlib import Path
import json,hashlib
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB
from unicorn.arm_const import *
b=Path('outputs/uvc-startup-fix/candidate-1080p/av-cam.bin').read_bytes();base=0x635c6000
u=Uc(UC_ARCH_ARM,UC_MODE_THUMB);u.mem_map(0x63000000,0x2000000);u.mem_write(base,b);u.mem_map(0x50000000,4096);u.mem_map(0x60000000,4096)
r={}
for func in [0x63a06dfc,0x63a06d28]:
 rows=[]
 for n in range(9):
  u.reg_write(UC_ARM_REG_CPSR,0x30);u.reg_write(UC_ARM_REG_R0,n);u.reg_write(UC_ARM_REG_SP,0x60000f00);u.reg_write(UC_ARM_REG_LR,0x50000001)
  u.emu_start(func|1,0x50000000,count=1000);assert u.reg_read(UC_ARM_REG_PC)==0x50000000
  p=u.reg_read(UC_ARM_REG_R0);s=bytes(u.mem_read(p,100)).split(b'\0')[0].decode();rows.append({'value':n,'label':s,'pointer':hex(p)})
 r[hex(func)]=rows
Path('outputs/yc-codec-recovery/enum-strings.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
