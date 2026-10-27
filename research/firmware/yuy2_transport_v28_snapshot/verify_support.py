"""Execute compiled ARM constructor/producer and Thumb bootstrap with bounded mocks."""
from pathlib import Path
import hashlib,json,struct
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
OUT=Path('.');ROOT=Path('.')
SB=0xa73d000;CB=0x4834000;MB=0x20000000;STOP=0x50000000;STACK=0x60010000
R=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]
SAVED=[UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]
def cstr(u,p):
 b=bytearray()
 while p and len(b)<4096:
  v=bytes(u.mem_read(p,1))[0];p+=1
  if not v:break
  b.append(v)
 return b.decode('ascii')
def put(u,p,x):u.mem_write(p,struct.pack('<I',x&0xffffffff))
def word(u,p):return struct.unpack('<I',u.mem_read(p,4))[0]
def load(u,p,base,imports=None):
 with Path(p).open('rb') as f:
  e=ELFFile(f);segs=[s for s in e.iter_segments() if s['p_type']=='PT_LOAD']
  end=max(s['p_vaddr']+s['p_memsz'] for s in segs);u.mem_map(base,(end+4095)&~4095)
  for s in segs:u.mem_write(base+s['p_vaddr'],s.data())
  names={}
  for sn in ['.symtab','.dynsym']:
   st=e.get_section_by_name(sn)
   if st:
    names.update({s.name:base+s['st_value'] for s in st.iter_symbols() if s.name and s['st_shndx']!='SHN_UNDEF'})
  for sn in ['.rel.dyn','.rel.plt']:
   rs=e.get_section_by_name(sn)
   if not rs:continue
   st=e.get_section(rs['sh_link'])
   for r in rs.iter_relocations():
    at=base+r['r_offset'];t=r['r_info_type']
    if t==23:put(u,at,word(u,at)+base)
    elif imports is not None and t in [21,22]:
     name=st.get_symbol(r['r_info_sym']).name
     put(u,at,imports(name))
  return names
class Case:
 def __init__(self,staging=0x200000,source=0x100000,wait=0,bad_guard=False,bad_symbol=False,bad_protect=False):
  self.u=u=Uc(UC_ARCH_ARM,UC_MODE_ARM);self.handlers={};self.calls=[];self.heap=0x40000000
  self.staging=staging;self.source=source;self.wait=wait;self.bad_symbol=bad_symbol;self.bad_protect=bad_protect
  for a,n in [(0x10000000,0x10000),(0x40000000,0x40000),(0x41000000,0x100000),(0x50000000,4096),(0x60000000,0x20000)]:u.mem_map(a,n)
  self.syms=load(u,OUT/'yuy2_640_v1.so',MB,self.imp)
  load(u,OUT.parent/'uvc-startup-fix/candidate-1080p/libInfraStreamingUsb.so',SB)
  load(u,ROOT/'dumps/camera_2025/usr/usr/lib/libInfraUsbCmn.so',CB)
  if bad_guard:u.mem_write(SB+0x8e14,b'\x00')
  self.handlers[self.syms['get_base']]=self.getbase
  u.hook_add(UC_HOOK_CODE,self.hook)
 def imp(self,name):
  addr=0x10000000+len(self.handlers)*4
  self.handlers[addr]=lambda n=name:self.imported(n)
  return addr
 def getbase(self):
  u=self.u;name=cstr(u,u.reg_read(R[0]));put(u,u.reg_read(R[1]),SB if 'StreamingUsb' in name else CB);return 0
 def imported(self,name):
  u=self.u;a=[u.reg_read(r) for r in R];sp=u.reg_read(UC_ARM_REG_SP)
  if name=='open':return 10 if cstr(u,a[0]).startswith('/proc/udm') else (11 if cstr(u,a[0])=='/dev/stream' else -1)
  if name in ['close','usleep','syscall','free']:return 0
  if name=='snprintf':self.calls.append(('log',cstr(u,a[3]),word(u,sp),word(u,sp+4),word(u,sp+8)));return 0
  if name=='mprotect':return -1 if self.bad_protect else 0
  if name=='strchr':
   s=cstr(u,a[0]);i=s.find(chr(a[1]));return a[0]+i if i>=0 else 0
  if name=='malloc':p=self.heap;self.heap=(p+a[0]+15)&~15;return p
  if name=='read':
   s=f'0401 0000050e 0002 01 01 00 01 00000001 12000000 {self.staging:08x} 0001\n'.encode();u.mem_write(a[1],s);return len(s)
  if name=='sscanf':
   vals=[int(x,16) for x in cstr(u,a[0]).split()[:10]]
   args=a[2:]+[word(u,sp+4*i) for i in range(8)]
   for p,v in zip(args,vals):put(u,p,v)
   return 10
  if name=='memcmp':return 0 if bytes(u.mem_read(a[0],a[2]))==bytes(u.mem_read(a[1],a[2])) else 1
  if name=='memcpy':u.mem_write(a[0],bytes(u.mem_read(a[1],a[2])));return a[0]
  if name=='memset':u.mem_write(a[0],bytes([a[1]&255])*a[2]);return a[0]
  if name=='dlopen':return 1
  if name=='dlsym':
   s=cstr(u,a[1]);return 0 if self.bad_symbol else self.imp('API:'+s)
  if name=='mmap':self.calls.append(('map',a[1]));return 0x41000000
  if name.startswith('API:'):
   if 'alloc_video_memory' in name and 'dealloc' not in name:
    assert a[1]==0x50f
    u.mem_write(a[2],struct.pack('<H',0x444));put(u,a[3],0x30000000);put(u,word(u,sp),self.source);self.calls.append(('alloc',a[1]));return 0
   if 'dealloc_video_memory' in name:self.calls.append(('free',));return 0
   if 'WaitVideoReadCmp' in name:return self.wait
   if 'UpdateVideoBufEvt' in name:self.calls.append(('submit',a[0],a[1]));return 0
   if 'judge_notify' in name:self.calls.append(('judge',a[2]));return 0
   if 'SendProbeInfo' in name or 'SendCommitInfo' in name:self.calls.append(('control',word(u,a[1]),word(u,a[1]+4)));return 0
  raise AssertionError(name)
 def hook(self,u,addr,size,user):
  if addr in self.handlers:
   result=self.handlers[addr]();u.reg_write(R[0],result&0xffffffff);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 def run(self,name,args=(),limit=12000000):
  u=self.u
  u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,STACK);u.reg_write(UC_ARM_REG_LR,STOP)
  for i,r in enumerate(SAVED):u.reg_write(r,0x71000000+i)
  for r,v in zip(R,args):u.reg_write(r,v)
  u.emu_start(self.syms[name],STOP,count=limit)
  assert u.reg_read(UC_ARM_REG_PC)==STOP,(name,hex(u.reg_read(UC_ARM_REG_PC)))
  assert u.reg_read(UC_ARM_REG_SP)==STACK,name
  assert [u.reg_read(r) for r in SAVED]==[0x71000000+i for i in range(8)],name
  return u.reg_read(R[0])