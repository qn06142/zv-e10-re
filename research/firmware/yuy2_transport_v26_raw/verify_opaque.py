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
  self.syms=v1.load(u,OUT/'yuy2_640_v26raw.so',MB,self.imp)
  v1.load(u,args.streaming_image.resolve(),SB)
  v1.load(u,v1.ROOT/'dumps/camera_2025/usr/usr/lib/libInfraUsbCmn.so',CB)
  if bad_guard:u.mem_write(SB+0x8e14,b'\x00')
  if bad_lifecycle_guard:u.mem_write(SB+0x7aa8,b'\x00')
  self.handlers[self.syms['get_base']]=self.getbase
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

results=[]
# Entire compiled ARM worker, mocked hardware. No Sony acquisition contract is invented.
c=Case().init();c.run('connect_hook',(STATE,MESSAGE));before=bytes(c.u.mem_read(0x41000000,614400))
assert c.run('produce',(SELF,SELF))==4 and count(c,'submit')==0
assert bytes(c.u.mem_read(0x41000000,614400))==before
assert logs(c,'RAW_SOURCE_ERROR')
results.append('no backend: no USB submission and no synthetic fallback')

def make_case(offset=0):
 c=Case().init();u=c.u;SRC=0x43000000;OPS=0x40038000
 u.mem_map(SRC,0x100000);pattern=bytes((i*37+19)&255 for i in range(0x100000));u.mem_write(SRC,pattern)
 state={'acq':0,'rel':0,'map':0,'unmap':0,'error':0,'release_error':0,'bytes':0x100000,'physical':0x31000000,'token':7,'order':[]}
 def acq():
  a=[u.reg_read(r) for r in v1.R];assert a[1]==10
  state['acq']+=1;state['order'].append('acquire')
  if state['error']:return state['error']
  # UNKNOWN format, zero flags, meaningless dimensions/stride deliberately accepted.
  u.mem_write(a[2],struct.pack('<12I',state['token'],123,3840,2160,0,0,state['physical'],state['bytes'],0,0,0,0));return 0
 def rel():
  assert u.reg_read(v1.R[1])==7;state['rel']+=1;state['order'].append('release');return state['release_error']
 def map_live():
  a=[u.reg_read(r) for r in v1.R];state['map']+=1;state['order'].append('map')
  at=v1.word(u,a[1]);assert at==0x31000000+offset and a[2]==614400
  u.mem_write(a[3],struct.pack('<3I',SRC+offset,SRC,614400));return 0
 def unmap_live():state['unmap']+=1;state['order'].append('unmap');return 0
 pointers=[]
 for handler in [acq,rel,map_live,unmap_live]:
  address=c.imp('RAW_CALLBACK');c.handlers[address]=handler;pointers.append(address)
 u.mem_write(OPS,struct.pack('<6I',1,24,*pointers))
 assert c.run('yuy2_raw_set_offset',(offset,))==0
 assert c.run('yuy2_live_bind',(OPS,0))==0
 c.run('connect_hook',(STATE,MESSAGE));return c,state,pattern
c,state,pattern=make_case();u=c.u;c.wait=1
before=bytes(u.mem_read(0x41000000,614400));assert c.run('produce',(SELF,SELF))==4
assert state['acq']==0 and bytes(u.mem_read(0x41000000,614400))==before
results.append('USB EBUSY prevents source acquisition and staging mutation')
c.wait=0;assert c.run('produce',(SELF,SELF))==0
assert bytes(u.mem_read(0x41000000,614400))==pattern[:614400]
assert state['order']==['acquire','map','unmap','release'] and count(c,'submit')==1
assert logs(c,'RAW_BYTES') and not logs(c,'LIVE_FALLBACK')
results.append('614400 bytes identical despite UNKNOWN format, flags0, foreign dimensions and stride0')
state['error']=-4;assert c.run('produce',(SELF,SELF))==4
assert count(c,'submit')==1 and bytes(u.mem_read(0x41000000,614400))==pattern[:614400]
results.append('acquisition timeout sends neither bars nor a repeated stale frame')
state['error']=0;state['release_error']=-7
assert c.run('produce',(SELF,SELF))==4;acquired=state['acq']
assert c.run('produce',(SELF,SELF))==4 and state['acq']==acquired and count(c,'submit')==1
results.append('failed release retains lease and prevents both submission and new acquisition')
state['release_error']=0
assert c.run('produce',(SELF,SELF))==0 and count(c,'submit')==2
results.append('cleanup retry recovers without inventing a new source reference')
c,state,pattern=make_case(4097)
assert c.run('produce',(SELF,SELF))==0
assert bytes(c.u.mem_read(0x41000000,614400))==pattern[4097:4097+614400]
assert c.run('yuy2_raw_set_offset',(0,))==0xfffffffa
results.append('unaligned byte-window offset preserved; active source offset changes rejected')
c,state,pattern=make_case();state['bytes']=614399
assert c.run('produce',(SELF,SELF))==4 and state['map']==0 and state['rel']==1 and count(c,'submit')==0
results.append('short allocation rejected before mapping, reference still released')
c,state,pattern=make_case(0xffffffff)
assert c.run('produce',(SELF,SELF))==4 and state['map']==0 and state['rel']==1 and count(c,'submit')==0
results.append('offset outside allocation rejected before mapping')

for physical in [0,0x30000000,0xfffff000]:
 c,state,pattern=make_case();state['physical']=physical
 assert c.run('produce',(SELF,SELF))==4 and state['map']==0 and state['rel']==1 and count(c,'submit')==0
 results.append('invalid/overlapping/wrapping source address rejected: '+hex(physical))
c,state,pattern=make_case();state['token']=0
assert c.run('produce',(SELF,SELF))==4 and state['map']==0 and state['rel']==0 and count(c,'submit')==0
results.append('missing stable reference rejected without a fabricated release')
(OUT/'opaque-integration-verification.json').write_text(json.dumps({'passed':len(results),'cases':results,'hardware_services_mocked':True,'Sony_backend_provided':False,'camera_access':False},indent=2))
print(json.dumps(results,indent=2))

