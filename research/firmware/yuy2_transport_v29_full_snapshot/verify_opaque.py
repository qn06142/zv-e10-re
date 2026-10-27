"""Execute the built ARM revision 2 hooks, failure paths and ownership contract."""
from pathlib import Path
import importlib.util,json,struct
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
spec=importlib.util.spec_from_file_location('v1',Path(__file__).with_name('verify_support.py'))
v1=importlib.util.module_from_spec(spec);spec.loader.exec_module(v1)
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
import argparse
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--repo',type=Path,required=True)
ap.add_argument('--output',type=Path,required=True)
ap.add_argument('--streaming-image',type=Path,required=True)
ap.add_argument('--stream-base',type=lambda v:int(v,0),default=v1.SB)
args=ap.parse_args();OUT=args.output.resolve();v1.ROOT=args.repo.resolve()
v1.SB=args.stream_base;SB=v1.SB;CB=v1.CB;MB=v1.MB
SELF=0x40030000;SM=0x40031000;STATE=0x40032000;MESSAGE=0x40033000

class Case(v1.Case):
 def __init__(self,wait_errno=16,staging=0x1c2000,source=0x320000,alloc_errors=(),wait=0,submit=0,
              phys=0x30000000,bad_guard=False,bad_symbol=False,bad_protect=False,
              bad_lifecycle_guard=False,map_error=False,free_error=0,event_error=0,
              complete_error=0,stop_error=False,device_error=False,unmap_error=False,
              protect_fail_at=0,staging_present=True,staging_base=0x12000000):
  self.u=u=Uc(UC_ARCH_ARM,UC_MODE_ARM);self.handlers={};self.calls=[];self.heap=0x40000000
  self.wait_errno=wait_errno;self.staging_present=staging_present;self.staging_base=staging_base
  self.staging=staging;self.source=source;self.wait=wait;self.bad_symbol=bad_symbol
  self.bad_protect=bad_protect;self.alloc_errors=list(alloc_errors);self.alloc_index=0
  self.phys=phys;self.map_error=map_error;self.free_error=free_error
  self.submit=submit;self.event_error=event_error;self.complete_error=complete_error
  self.stop_error=stop_error;self.device_error=device_error;self.unmap_error=unmap_error
  self.protect_fail_at=protect_fail_at;self.protect_calls=0;self.tramp_count=0;self.locked={}
  self.alloc_sizes={};self.free_blocks=[]
  for a,n in [(0x10000000,0x10000),(0x40000000,0x40000),(0x41000000,0x100000),
              (0x42000000,0x10000),(0x50000000,4096),(0x60000000,0x20000)]:u.mem_map(a,n)
  self.syms=v1.load(u,OUT/'yuy2_640_v29full.so',MB,self.imp)
  v1.load(u,args.streaming_image.resolve(),SB)
  v1.load(u,v1.ROOT/'dumps/camera_2025/usr/usr/lib/libInfraUsbCmn.so',CB)
  if bad_guard:u.mem_write(SB+0x8e14,b'\x00')
  if bad_lifecycle_guard:u.mem_write(SB+0x7aa8,b'\x00')
  self.handlers[self.syms['get_base']]=self.getbase
  u.mem_map(0x44000000,0x400000)
  u.hook_add(UC_HOOK_CODE,self.hook)
  u.mem_write(SELF,b'\x01');v1.put(u,SELF+0x10,0x710);v1.put(u,SELF+0x14,0x714);v1.put(u,SELF+0x18,0x718)
  v1.put(u,SM+0x34,SELF);v1.put(u,SM+8,0x999);v1.put(u,SM+0x18,0x1234)
  v1.put(u,MESSAGE+4,0x5678)
 def originals(self):
  for name in ['connect','start','stop','finish']:
   v1.put(self.u,self.syms['original_'+name],self.imp('ORIG:'+name))
 def init(self):
  self.run('yuy2_activate');assert self.run('yuy2_status')==1;self.originals();return self
 def imported(self,name):
  u=self.u;a=[u.reg_read(r) for r in v1.R];sp=u.reg_read(UC_ARM_REG_SP)
  if name=='__errno_location':return 0x4003f000
  if name=='gettimeofday':u.mem_write(a[0],struct.pack('<II',100,1000));return 0
  if name=='malloc' and a[0]==4194304:return 0x44000000
  if name=='malloc':
   found=next((i for i,(_,size) in enumerate(self.free_blocks) if size>=a[0]),None)
   if found is None:p=super().imported(name);size=a[0]
   else:p,size=self.free_blocks.pop(found)
   self.alloc_sizes[p]=size;return p
  if name=='free':
   if a[0] in self.alloc_sizes:self.free_blocks.append((a[0],self.alloc_sizes.pop(a[0])))
   return 0
  if name=='open':
   path=v1.cstr(u,a[0]);return 10 if path.startswith('/proc/udm') else ((-1 if self.device_error else 11) if path=='/dev/stream' else -1)
  if name=='read':
   s=(f'0401 0000050e 0002 01 01 00 01 00000001 {self.staging_base:08x} {self.staging:08x} 0001\n' if self.staging_present else 'Information on Units.\n').encode()
   u.mem_write(a[1],s);return len(s)
  if name=='sscanf':
   try:[int(x,16) for x in v1.cstr(u,a[0]).split()[:10]]
   except ValueError:return 0
  if name=='mmap':
   if a[3]==0x22:
    p=0x42000000+self.tramp_count*4096;self.tramp_count+=1;return p
   self.calls.append(('map',a[1]));return -1 if self.map_error else 0x41000000
  if name=='munmap':self.calls.append(('unmap',a[0],a[1]));return -1 if self.unmap_error else 0
  if name=='usleep':self.calls.append(('sleep',a[0]));return 0
  if name=='mprotect':
   self.protect_calls+=1
   return -1 if self.bad_protect or self.protect_calls==self.protect_fail_at else 0
  if name.startswith('ORIG:'):
   self.calls.append((name,a[0]))
   if name=='ORIG:stop':
    if not self.stop_error:u.mem_write(a[0],b'\x01')
    return 4 if self.stop_error else 0
   if name=='ORIG:start':u.mem_write(a[0],b'\x02')
   if name=='ORIG:finish':u.mem_write(a[0],b'\x00')
   return 0
  if name.startswith('API:'):
   if 'alloc_video_memory' in name and 'dealloc' not in name:
    assert a[1]==0x276,'Audio allocation regression'
    self.calls.append(('alloc',a[1]));err=self.alloc_errors[self.alloc_index] if self.alloc_index<len(self.alloc_errors) else 0;self.alloc_index+=1
    if not err:
     u.mem_write(a[2],struct.pack('<H',0x444));v1.put(u,a[3],self.phys);v1.put(u,v1.word(u,sp),self.source)
    return err
   if 'dealloc_video_memory' in name:self.calls.append(('free',v1.word(u,a[1])&0xffff));return self.free_error
   if name.endswith('_ZN3UFW3Sem4LockEv'):
    assert not self.locked.get(a[0]);self.locked[a[0]]=True;self.calls.append(('lock',a[0]));return 0
   if name.endswith('_ZN3UFW3Sem6UnlockEv'):
    assert self.locked.get(a[0]);self.locked[a[0]]=False;self.calls.append(('unlock',a[0]));return 0
   if 'getStateMachine' in name:return SM
   if 'sendCompMsg' in name:
    self.calls.append(('complete',a[0],v1.word(u,a[1]),v1.word(u,a[1]+4)));return self.complete_error
   if 'changeState' in name:v1.put(u,a[0],a[1]);self.calls.append(('state',a[1]));return 0
   if name.endswith('SendEvtStreamingMain'):self.calls.append(('event',a[0]));return self.event_error
   if 'WaitVideoReadCmp' in name:
    v1.put(u,0x4003f000,self.wait_errno if self.wait else 0)
    self.calls.append(('wait',self.wait));return self.wait
   if 'UpdateVideoBufEvt' in name:self.calls.append(('submit',a[0],a[1]));return self.submit
  return super().imported(name)

def count(c,n):return sum(x[0]==n for x in c.calls)
def logs(c,n):return [x for x in c.calls if x[:2]==('log',n)]


import zlib
from reassemble import decode
c=Case().init();u=c.u;CTX=0x40039000;OPS=0x40038000;SRC=0x43000000
u.mem_map(SRC,0x200000);pattern=bytes((i*19+(i>>9))&255 for i in range(2073600));u.mem_write(SRC,pattern)
commands=[];pending={'reply':False,'receive':True};seen=[]
def select_native():
 a=[u.reg_read(r) for r in v1.R];u.mem_write(a[1],struct.pack('<H2xI',0x408a,0x295));return 0
def send_native():
 a=[u.reg_read(r) for r in v1.R];raw=bytes(u.mem_read(a[1],24));commands.append(struct.unpack_from('<H',raw)[0]);pending['reply']=True;return 0
def receive_native():
 if not pending['receive'] or not pending['reply']:return 1
 pending['reply']=False;a=[u.reg_read(r) for r in v1.R];raw=bytearray(24)
 struct.pack_into('<6H',raw,0,commands[-1]|0x8000,0,0x408a,0x5678,1,0)
 struct.pack_into('<II',raw,16,0x18000000,2073600);u.mem_write(a[1],bytes(raw));return 0
def map_native():
 a=[u.reg_read(r) for r in v1.R];assert v1.word(u,a[1])==0x18000000 and a[2]==2073600
 u.mem_write(a[3],struct.pack('<3I',SRC,SRC,2073600));return 0
def crc_fixture():
 a=[u.reg_read(r) for r in v1.R];return zlib.crc32(bytes(u.mem_read(a[0],a[1])))
# CRC arithmetic is separately exercised by compiled C fixture; mock it here
# to keep instruction-by-instruction ARM lifecycle execution inexpensive.
c.handlers[c.syms['crc']]=crc_fixture
pointers=[]
for handler in [select_native,send_native,receive_native,map_native,lambda:0]:
 address=c.imp('NATIVE_TEST');c.handlers[address]=handler;pointers.append(address)
u.mem_write(CTX,struct.pack('<5I',*pointers[:3],0,0x12345678)+bytes(80))
u.mem_write(OPS,struct.pack('<6I',1,24,c.syms['native_dmm_acquire'],c.syms['native_dmm_release'],*pointers[3:]))
assert c.run('yuy2_live_bind',(OPS,CTX))==0
c.run('connect_hook',(STATE,MESSAGE));pending['receive']=False
assert c.run('produce',(SELF,SELF))==4 and commands==[2] and count(c,'submit')==0
pending['receive']=True
assert c.run('produce',(SELF,SELF))==0 and commands==[2,5,6,4]
seen.append(bytes(u.mem_read(0x41000000,614400)))
# Failed USB submission must leave chunk offset unchanged for exact retry.
c.submit=1
assert c.run('produce',(SELF,SELF))==4
retry=bytes(u.mem_read(0x41000000,614400));c.submit=0
assert c.run('produce',(SELF,SELF))==0 and bytes(u.mem_read(0x41000000,614400))==retry
seen.append(retry)
u.mem_write(SRC,bytes([0xa7])*2073600)
for _ in range(2):
 assert c.run('produce',(SELF,SELF))==0;seen.append(bytes(u.mem_read(0x41000000,614400)))
complete,incomplete=decode(b''.join(seen));assert not incomplete and complete[0][1]==pattern
assert commands==[2,5,6,4] and v1.word(u,CTX+32)==0 and v1.word(u,CTX+36)==0
assert c.run('stop_hook',(SELF,))==0
assert v1.word(u,c.syms['snapshot']+28)==0 # ready flag, ARM struct offsets
report={'camera_access':False,'compiled_ARM_worker':True,'native_protocol_commands':commands,'complete_allocation_bytes':len(pattern),'chunks':len(seen),'exact_reassembly':True,'submission_retry_preserved_chunk':True,'crc_mocked_in_ARM_test':True,'crc_tested_in_compiled_host_fixture':True}
(OUT/'full-snapshot-integration.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
