"""Execute actual compiled ARM load_calls with real Sony ELF prologues and captured maps.
Only libc/loader/procfs and Sony constructors are mocked; no target writes.
"""
from pathlib import Path
import argparse, importlib.util, json, re, struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *
from elftools.elf.elffile import ELFFile
ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--workspace',type=Path,default=Path.cwd());a=ap.parse_args()
ROOT=a.workspace.resolve()
spec=importlib.util.spec_from_file_location('support',Path(__file__).parent/'recipe/verify_support.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
MAPS=(ROOT/'.local/outputs/vga-v30/logpull-20261028/obs-maps.txt').read_bytes()
SDK_BASE=0x05792000;OBJ_BASE=0x06592000
SONY=a.repo/'.local/dumps/camera_2025/usr/usr/lib'
R=m.R
class Case:
 def __init__(self,module,chunk=2048,data=MAPS,fail_read=False,bad_sdk=False,bad_obj=False,missing=False,zero_queue=False):
  self.u=u=Uc(UC_ARCH_ARM,UC_MODE_ARM);self.handlers={};self.trace=[];self.ctors=[];self.outcome=None;self.offset=0;self.reads=0
  self.chunk=chunk;self.data=data;self.fail_read=fail_read;self.missing=missing;self.zero_queue=zero_queue
  for addr,size in [(0x10000000,0x10000),(m.STOP,4096),(0x60000000,0x20000)]:u.mem_map(addr,size)
  self.syms=m.load(u,module,m.MB,self.imp)
  self.sdk=m.load(u,SONY/'libBizFw.so',SDK_BASE)
  m.load(u,SONY/'libObj.so',OBJ_BASE)
  guards=json.loads((Path(__file__).parent/'recipe/vga_guards.json').read_text())
  for key in ['DMM_CTOR','SDF_CTOR']:
   addr=self.sdk[guards['sdk'][key]['symbol']]&~1
   self.handlers[addr]=lambda key=key:self.ctor(key)
  addr=OBJ_BASE+int(guards['obj']['ALLOC_CTOR']['address'],16)
  self.handlers[addr]=lambda:self.ctor('ALLOC_CTOR')
  if bad_sdk:u.mem_write(self.sdk[guards['sdk']['SHARE']['symbol']]&~1,b'\x00')
  if bad_obj:u.mem_write(OBJ_BASE+int(guards['obj']['GEOMETRY']['address'],16),b'\x00')
  u.hook_add(UC_HOOK_CODE,self.hook)
 def ctor(self,key):
  self.ctors.append(key);p=self.u.reg_read(R[0]);off=8 if key=='ALLOC_CTOR' else 4
  m.put(self.u,p+off,0 if self.zero_queue else 0x123400+len(self.ctors));return 0
 def imp(self,name):
  addr=0x10000000+len(self.handlers)*4;self.handlers[addr]=lambda name=name:self.call(name);return addr
 def call(self,name):
  u=self.u;v=[u.reg_read(r) for r in R];sp=u.reg_read(UC_ARM_REG_SP)
  if name=='dlopen':return 1 if m.cstr(u,v[0])=='libBizFw.so' else 2
  if name=='dlsym':return 0 if self.missing else self.sdk[m.cstr(u,v[1])]
  if name=='memset':u.mem_write(v[0],bytes([v[1]&255])*v[2]);return v[0]
  if name=='memcpy':u.mem_write(v[0],bytes(u.mem_read(v[1],v[2])));return v[0]
  if name=='memcmp':return 0 if bytes(u.mem_read(v[0],v[2]))==bytes(u.mem_read(v[1],v[2])) else 1
  if name=='open':return 10 if m.cstr(u,v[0])=='/proc/self/maps' else 11
  if name=='close':return 0
  if name=='read':
   assert v[0]==10;self.reads+=1
   if self.fail_read and self.offset:return -1
   n=min(v[2],self.chunk,len(self.data)-self.offset)
   if n:u.mem_write(v[1],self.data[self.offset:self.offset+n]);self.offset+=n
   return n
  if name=='snprintf':
   tag=m.cstr(u,v[3]);self.trace.append(tag)
   if tag in ['QUEUES','GUARD_FAILED']:
    self.outcome=0 if tag=='QUEUES' else 0xffffffff
    u.emu_stop()
   return 0
  if name=='sscanf':
   assert m.cstr(u,v[1])=='%x-%x %7s %x %*s %*s %255s'
   match=re.match(r'([0-9a-f]+)-([0-9a-f]+)\s+(\S+)\s+([0-9a-f]+)\s+\S+\s+\S+\s+(\S+)',m.cstr(u,v[0]))
   if not match:return 4
   args=v[2:]+[m.word(u,sp+i*4) for i in range(3)]
   for p,value in zip(args,[int(match[1],16),int(match[2],16),match[3],int(match[4],16),match[5]]):
    if isinstance(value,int):m.put(u,p,value)
    else:u.mem_write(p,value.encode()+b'\x00')
   return 5
  raise AssertionError(name)
 def hook(self,u,addr,size,user):
  if addr in self.handlers:
   result=self.handlers[addr]();u.reg_write(R[0],result&0xffffffff);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 def run(self):
  u=self.u;u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,m.STACK);u.reg_write(UC_ARM_REG_LR,m.STOP)
  u.emu_start(self.syms['worker'],m.STOP,count=20000000)
  assert self.outcome is not None, self.trace
  return self.outcome
old=ROOT/'.local/outputs/vga-v30/build/yuy2_640_v30vga.so';new=ROOT/'.local/outputs/vga-v31/build/yuy2_640_v31vga.so'
results=[]
def check(name,module,success,tag=None,**kw):
 c=Case(module,**kw);rc=c.run();assert (rc==0)==success,(name,rc,c.trace)
 if tag:assert tag in c.trace,(name,c.trace)
 if success:assert c.ctors==['DMM_CTOR','SDF_CTOR','ALLOC_CTOR'] and c.offset==len(c.data)
 elif not kw.get('zero_queue'):assert not c.ctors,(name,c.ctors)
 results.append(dict(case=name,success=success,read_calls=c.reads,bytes_read=c.offset,markers=c.trace))
check('old_single_read_fails_captured_maps_2KiB_chunks',old,False)
check('old_single_read_passes_same_maps_when_read_whole',old,True,chunk=131071)
for chunk in [1,127,2048,4096,8192,131071]:check('new_full_maps_chunk_'+str(chunk),new,True,'QUEUES',chunk=chunk)
check('read_error_rejected',new,False,'MAPS_READ_FAILED',fail_read=True)
check('missing_obj_rejected',new,False,'OBJ_MAPPING_MISSING',data=b'00001000-00002000 r-xp 00000000 00:00 0 /test.so\n')
check('empty_maps_rejected',new,False,'MAPS_EMPTY',data=b'')
check('oversized_maps_rejected',new,False,'MAPS_TOO_LARGE',data=b'x'*131072)
check('exact_capacity_eof_accepted',new,True,'QUEUES',data=MAPS+b'\n'*(131071-len(MAPS)))
check('sdk_guard_preserved',new,False,'SDK_GUARD_MISMATCH',bad_sdk=True)
check('obj_guard_preserved',new,False,'OBJ_GUARD_MISMATCH',bad_obj=True)
check('missing_symbol_rejected',new,False,'SDK_SYMBOL_MISSING',missing=True)
check('zero_queues_rejected',new,False,'QUEUE_INIT_FAILED',zero_queue=True)
out=dict(camera_access=False,compiled_ARM_worker_initialization_executed=True,real_Sony_ELF_prologues=True,captured_maps_bytes=len(MAPS),cases=results,limitations=['Procfs chunking and loader calls mocked; exact failed target branch was not logged in 3.0.','No live VGA image or SDF acceptance proof.'])
p=ROOT/'.local/outputs/vga-v31/loader-verification.json';p.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
