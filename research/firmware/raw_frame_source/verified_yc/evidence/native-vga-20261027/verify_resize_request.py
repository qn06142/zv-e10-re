from pathlib import Path
import json,struct,hashlib
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_HOOK_CODE
from unicorn.arm_const import *
OUT=Path('outputs/yc-vga-test');ROOT=Path(r'D:/02_Development_And_Projects/pmca-re/dumps/camera_2025/usr/usr/lib')
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
rows=[]
for entry in [0x18a58c,0x19fc88]:
 for sh,ss,dh,ds in [(0x1234,0x01020304,0x5678,0x11223344),(1,0,2,0),(0xfffe,1,0xabcd,2)]:
  u=elf_machine('libObj.so');capture=[]
  def hook(u,a,n,d):
   if a in [0x172a4c,0x10d33c,0x10c75c]:ret(u)
   elif a==0x108d34:
    capture.append(bytes(u.mem_read(u.reg_read(UC_ARM_REG_R3),68)));ret(u)
  u.hook_add(UC_HOOK_CODE,hook)
  u.mem_write(DATA+0x100,struct.pack('<HHI',sh,0xa5a5,ss));u.mem_write(DATA+0x200,struct.pack('<HHI',dh,0x5a5a,ds))
  assert run(u,entry,[DATA,DATA+0x100,DATA+0x200])==0
  assert len(capture)==1;c=capture[0];expected=bytearray(68)
  struct.pack_into('<I',expected,0x18,ss);struct.pack_into('<H',expected,0x1c,sh);expected[0x25]=1
  struct.pack_into('<I',expected,0x38,ds);struct.pack_into('<H',expected,0x3c,dh)
  assert c==bytes(expected),(hex(entry),c.hex(),expected.hex())
  # Run original SDK wrapper too; only logging and actual hardware send/receive are mocked.
  sdk=elf_machine('libBizFw.so');sent=[]
  def sdkhook(u,a,n,d):
   if a in [0x2cbc4,0x2b004]:ret(u)
   elif a==0x2bf7c:
    sp=u.reg_read(UC_ARM_REG_SP);ackbytes,ptr,size=struct.unpack('<III',u.mem_read(sp,12))
    assert ackbytes==16 and size==68 and u.reg_read(UC_ARM_REG_R2)==24
    sent.append(bytes(u.mem_read(ptr,size)));ret(u)
  sdk.hook_add(UC_HOOK_CODE,sdkhook)
  sdk.mem_write(DATA+4,struct.pack('<IH',0x00611234,0x35));sdk.mem_write(DATA+0x300,c)
  assert run(sdk,0x369b4,[DATA,DATA+0x500,DATA+0x600,DATA+0x300])==0
  header=struct.pack('<10H',0x2000,3,68,0,7,*([0x1234]*5))
  assert len(sent)==1 and sent[0]==header+c[20:]
  rows.append({'caller':hex(entry),'source_reference':[sh,ss],'destination_reference':[dh,ds],'sdk_command_hex':sent[0].hex()})
  if entry==0x18a58c and ss==0:(OUT/'resize-request-example-NOT-FOR-DEVICE.bin').write_bytes(sent[0])
report={'camera_access':False,'native_original_instructions_executed':True,'mocked':['debug/logging','SdfCh constructor/destructor in caller','sendAndRcvAckCmp in SDK wrapper'],'live_hardware_acceptance_proved':False,'reference_layout':{'handle_offset':0,'unit_type_offset':4,'evidence':'libObj allocNewSdsAndYc 0x206b58 and allocator 0x206aec; word4 stores allocation unit type, not address/data_site'},'cases':rows,'binary_md5':{n:hashlib.md5((ROOT/n).read_bytes()).hexdigest() for n in ['libObj.so','libBizFw.so']}}
(OUT/'resize-request-verification.json').write_text(json.dumps(report,indent=2)+'\n');print('PASS: six original caller + SDK wrapper fixtures; exact 68-byte requests; no camera access')
