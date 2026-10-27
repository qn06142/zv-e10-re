from pathlib import Path
import struct,json
from unicorn import *
from unicorn.arm_const import *
B=Path('outputs/uvc-startup-fix/candidate-1080p/av-cam.bin').read_bytes();BASE=0x635c6000;DATA=0x50000000;STOP=0x60000000
rows=[]
for w,h,comp in [(640,480,0),(640,480,1),(1920,1080,0),(1920,1080,1)]:
 u=Uc(UC_ARCH_ARM,UC_MODE_THUMB);u.mem_map(0x63000000,0x2000000);u.mem_write(BASE,B);u.mem_map(DATA,0x20000);u.mem_map(STOP,4096);seen=[]
 info=bytearray(56);struct.pack_into('<I',info,4,0);struct.pack_into('<H',info,8,0x1234);struct.pack_into('<HH',info,0x18,w,h);info[0x2f]=comp
 def ret(v=0):u.reg_write(UC_ARM_REG_R0,v);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 def hook(u,a,n,d):
  if a in [0x636bae70,0x636bae58,0x63ca26d8]:ret()
  elif a==0x636ba47c:u.mem_write(u.reg_read(UC_ARM_REG_R2),bytes(info));ret()
  elif a==0x63ca46ea:seen.append(u.reg_read(UC_ARM_REG_R2));ret()
 u.hook_add(UC_HOOK_CODE,hook);u.reg_write(UC_ARM_REG_CPSR,0x30);u.reg_write(UC_ARM_REG_SP,DATA+0x18000);u.reg_write(UC_ARM_REG_LR,STOP|1)
 for r,v in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2],[DATA,DATA+0x100,DATA+0x200]):u.reg_write(r,v)
 u.emu_start(0x63ca47b9,STOP,count=10000);assert u.reg_read(UC_ARM_REG_PC)==STOP
 assert seen==[w*h*(1 if comp==1 else 2)]
 rows.append({'canvas':[w,h],'yc_compress':comp,'requested_capacity':seen[0]})
Path('outputs/yc-vga-test/capacity-check-verification.json').write_text(json.dumps({'original_function':'0x63ca47b8','camera_access':False,'metadata_read_and_capacity_operation_mocked':True,'proved':'byte count passed by resolver, not hardware format/acceptance','cases':rows},indent=2)+'\n');print('PASS: four original RTOS capacity-path fixtures',rows)
