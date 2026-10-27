from pathlib import Path
import json,struct,hashlib
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_HOOK_CODE
from unicorn.arm_const import *
OUT=Path('outputs/vga-v30');ROOT=Path(r'D:/02_Development_And_Projects/pmca-re/dumps/camera_2025/usr/usr/lib')
REGS=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]
STOP=0x60000000;DATA=0x50000000;STACK=DATA+0x18000

def elf_machine(name):
 u=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
 with (ROOT/name).open('rb') as f:
  e=ELFFile(f);segs=[s for s in e.iter_segments() if s['p_type']=='PT_LOAD'];top=max(s['p_vaddr']+s['p_memsz'] for s in segs)
  u.mem_map(0,(top+4095)&~4095)
  for s in segs:u.mem_write(s['p_vaddr'],s.data())
 u.mem_map(DATA,0x20000);u.mem_map(STOP,4096)
 return u

def run(u,entry,args):
 u.reg_write(UC_ARM_REG_CPSR,0x30);u.reg_write(UC_ARM_REG_SP,STACK);u.reg_write(UC_ARM_REG_LR,STOP|1)
 for r,v in zip(REGS,args):u.reg_write(r,v)
 u.emu_start(entry|1,STOP,count=50000)
 assert u.reg_read(UC_ARM_REG_PC)==STOP
 return u.reg_read(UC_ARM_REG_R0)

def ret(u,v=0):u.reg_write(UC_ARM_REG_R0,v);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))

u=elf_machine('libObj.so');calls=[]
def hook(u,a,n,d):
 if a==0x1756dc:
  calls.append([u.reg_read(UC_ARM_REG_R0),u.reg_read(UC_ARM_REG_R1)]);ret(u,4)
u.hook_add(UC_HOOK_CODE,hook)
geometry=struct.pack('<10H',640,480,0,0,640,480,0,0,640,480)
u.mem_write(DATA+0x1000,geometry)
run(u,0xe48a10,[DATA,DATA+0x1000])
wire=bytes(u.mem_read(DATA+0x124,60))
assert struct.unpack_from('<10H',wire,0x18)==(640,480,0,0,640,480,0,0,640,480)
assert wire[0x2f]==0 and wire[0x2e]==4
assert calls==[[640,480]]
Path('outputs/vga-v30/original-geometry-verification.json').write_text(json.dumps({'camera_access':False,'original_geometry_method':'0xe48a10','only_aspect_classifier_mocked':True,'canvas':[640,480],'valid':[0,0,640,480],'target':[0,0,640,480],'yc_compress_not_modified_by_geometry_method':True,'passed':True},indent=2)+'\n')
print('PASS: original Sony VGA geometry method writes expected metadata offsets')

