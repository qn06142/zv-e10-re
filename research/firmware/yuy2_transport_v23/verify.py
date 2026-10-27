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
 def __init__(self,staging=0x1c2000,source=0x320000,alloc_errors=(),wait=0,submit=0,
              phys=0x30000000,bad_guard=False,bad_symbol=False,bad_protect=False,
              bad_lifecycle_guard=False,map_error=False,free_error=0,event_error=0,
              complete_error=0,stop_error=False,device_error=False,unmap_error=False,
              protect_fail_at=0,staging_present=True,staging_base=0x12000000):
  self.u=u=Uc(UC_ARCH_ARM,UC_MODE_ARM);self.handlers={};self.calls=[];self.heap=0x40000000
  self.staging_present=staging_present;self.staging_base=staging_base
  self.staging=staging;self.source=source;self.wait=wait;self.bad_symbol=bad_symbol
  self.bad_protect=bad_protect;self.alloc_errors=list(alloc_errors);self.alloc_index=0
  self.phys=phys;self.map_error=map_error;self.free_error=free_error
  self.submit=submit;self.event_error=event_error;self.complete_error=complete_error
  self.stop_error=stop_error;self.device_error=device_error;self.unmap_error=unmap_error
  self.protect_fail_at=protect_fail_at;self.protect_calls=0;self.tramp_count=0;self.locked={}
  self.alloc_sizes={};self.free_blocks=[]
  for a,n in [(0x10000000,0x10000),(0x40000000,0x40000),(0x41000000,0x100000),
              (0x42000000,0x10000),(0x50000000,4096),(0x60000000,0x20000)]:u.mem_map(a,n)
  self.syms=v1.load(u,OUT/'yuy2_640_v23.so',MB,self.imp)
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
  self.run('install');assert self.run('yuy2_status')==1;self.originals();return self
 def imported(self,name):
  u=self.u;a=[u.reg_read(r) for r in v1.R];sp=u.reg_read(UC_ARM_REG_SP)
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
   if 'WaitVideoReadCmp' in name:self.calls.append(('wait',self.wait));return self.wait
   if 'UpdateVideoBufEvt' in name:self.calls.append(('submit',a[0],a[1]));return self.submit
  return super().imported(name)

def count(c,n):return sum(x[0]==n for x in c.calls)
def logs(c,n):return [x for x in c.calls if x[:2]==('log',n)]
results=[]
for kind,params in [('normal',{}),('code_guard',{'bad_guard':True}),('lifecycle_guard',{'bad_lifecycle_guard':True}),
                    ('symbol',{'bad_symbol':True}),('trampoline_protection',{'bad_protect':True}),
                    ('stream_protection',{'protect_fail_at':5}),('common_protection',{'protect_fail_at':6}),
                    ('table_protection',{'protect_fail_at':7})]:
 c=Case(**params);before=bytes(c.u.mem_read(SB+0x7000,0x3000));c.run('install')
 assert c.run('yuy2_status')==(kind=='normal'),kind
 if kind!='normal':assert before==bytes(c.u.mem_read(SB+0x7000,0x3000)),kind
 else:
  for i,off in enumerate([0x1cab8,0x1cdb0]):
   assert v1.word(c.u,CB+off)==77
   assert bytes(c.u.mem_read(v1.word(c.u,CB+off+4),77))==(OUT/'descriptors.bin').read_bytes()[i*77:(i+1)*77]
 results.append('constructor:'+kind)

# Execute every real trampoline prefix and Thumb -> original-code continuation.
c=Case();c.run('install')
for i,off in enumerate([0x7aa8,0x903e,0x8f9c,0x8dbe]):
 u=c.u;p=0x42000000+i*4096
 decoded=list(Cs(CS_ARCH_ARM,CS_MODE_THUMB).disasm(bytes(u.mem_read(p,20)),p))
 assert sum(x.size for x in decoded)==20
 u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,v1.STACK);u.reg_write(UC_ARM_REG_LR,v1.STOP)
 u.reg_write(UC_ARM_REG_R0,SELF);u.reg_write(UC_ARM_REG_R1,MESSAGE)
 u.emu_start(p|1,SB+off+10,count=100)
 assert u.reg_read(UC_ARM_REG_PC)==SB+off+10
 results.append('trampoline:'+hex(off))

c=Case().init();assert c.run('connect_hook',(STATE,MESSAGE))==0
assert count(c,'ORIG:connect')==1 and count(c,'alloc')==1 and not count(c,'complete')
assert c.run('start_hook',(SELF,))==0
assert c.run('produce',(SELF,SELF))==0
assert bytes(c.u.mem_read(0x41000000,614400))==(OUT/'expected-frame-00000.yuy2').read_bytes()
assert ('submit',614400,0x30000000) in c.calls
c.run('produce',(SELF,SELF));assert count(c,'alloc')==1
assert c.u.mem_read(0x41000000+472*1280,1)==b'\xeb'
results.append('producer:golden_frame_counter_and_owned_workspace')

c=Case(alloc_errors=[4,4,0]).init();assert c.run('connect_hook',(STATE,MESSAGE))==0
assert count(c,'alloc')==3 and c.calls.count(('sleep',150000))==2
results.append('connect:transient_failure_retries_then_success')

for name,params in [('allocation',{'alloc_errors':[4]*10}),
                    ('short_source',{'source':0x1800}),('zero_source',{'phys':0}),
                    ('overflow',{'phys':0xfff00000}),('map',{'map_error':True}),('device',{'device_error':True})]:
 c=Case(**params).init();assert c.run('connect_hook',(STATE,MESSAGE))==4,name
 assert not count(c,'ORIG:connect') and not count(c,'submit'),name
 assert count(c,'complete')==1 and c.calls[-2][0] in ('complete','log')
 assert c.calls.count(('sleep',150000))==4,name
 assert count(c,'alloc')==(0 if name=='staging' else 5),name
 assert any(x[:2]==('complete',0x5678) and x[2:]==(0x2003,0x10000003) for x in c.calls)
 if name in ['short_source','zero_source','overflow','map','device']:assert count(c,'free')==5,name
 if name in ['short_source','zero_source','overflow']:assert not count(c,'map'),name
 results.append('connect:bounded_'+name+'_failure_completes_before_starting')

c=Case(alloc_errors=[4]*5).init();assert c.run('connect_hook',(STATE,MESSAGE))==4
c.alloc_errors=[];assert c.run('connect_hook',(STATE,MESSAGE))==0
results.append('connect:later_request_recovers_without_process_restart')

for name,params in [('wait',{'wait':1}),('submit',{'submit':1})]:
 c=Case(**params).init();c.run('connect_hook',(STATE,MESSAGE));c.u.mem_write(SELF,b'\x02')
 for _ in range(6):assert c.run('produce',(SELF,SELF))==4
 assert c.calls.count(('event',10))==1
 assert count(c,'free')==0 # worker must not free a possibly active DMA source
 c.wait=0;assert c.run('failure_hook',(STATE,MESSAGE))==0
 assert v1.word(c.u,SM+0x18)==0 and v1.word(c.u,SM)==0x999
 assert c.u.mem_read(SELF,1)==b'\x01' and count(c,'free')==0
 assert not any(c.locked.values())
 results.append('runtime:'+name+'_failure_defers_stop_and_replies_on_main_queue')

c=Case().init();c.run('connect_hook',(STATE,MESSAGE));c.run('produce',(SELF,SELF))
c.wait=1;c.run('stop_hook',(SELF,));assert not count(c,'free') and not any(x[0]=='unmap' and x[1]==0x41000000 for x in c.calls)
c.wait=0;c.run('finish_hook',(SELF,));assert count(c,'free')==0 and v1.word(c.u,c.syms['manager'])==0
results.append('ownership:uncertain_dma_pinned_until_completion')

c=Case(free_error=4).init();c.run('connect_hook',(STATE,MESSAGE));assert c.run('cleanup_source')==32
assert v1.word(c.u,c.syms['handle'])&0xffff==0x444
assert c.run('ensure_source',(SELF,))==34 and count(c,'alloc')==1
results.append('ownership:free_failure_retains_handle_and_prevents_second_allocation')

c=Case(stop_error=True).init();c.run('connect_hook',(STATE,MESSAGE));c.u.mem_write(SELF,b'\x02')
assert c.run('failure_hook',(STATE,MESSAGE))==4 and not count(c,'free') and not count(c,'complete')
results.append('recovery:stop_failure_does_not_free_or_fabricate_completion')

c=Case(complete_error=7).init();c.run('connect_hook',(STATE,MESSAGE));c.u.mem_write(SELF,b'\x02')
assert c.run('failure_hook',(STATE,MESSAGE))==4 and v1.word(c.u,SM+0x18)==0x1234
assert not count(c,'state')
results.append('recovery:reply_failure_preserves_pending_token')

c=Case(event_error=1).init();c.run('connect_hook',(STATE,MESSAGE));v1.put(c.u,c.syms['recovering'],1)
for _ in range(9):c.run('produce',(SELF,SELF))
assert count(c,'event')==5
results.append('recovery:event_queue_attempts_bounded')

c=Case().init();v1.put(c.u,CB+0x1f108,0x40034000)
for n in ['probe','commit']:assert c.run(n,(0,333333))==0
assert [x for x in c.calls if x[0]=='control']==[('control',0x01010000,1000000)]*2
results.append('control:format_and_interval')

# Real lifecycle regression: Ready connect precedes gadget staging allocation.
c=Case(staging_present=False).init();assert c.run('connect_hook',(STATE,MESSAGE))==0
assert count(c,'alloc')==1 and not count(c,'complete')
results.append('ordering:connect_allows_driver_to_allocate_staging_later')
for _ in range(4):assert c.run('produce',(SELF,SELF))==4
assert not count(c,'submit') and not count(c,'event')
c.staging_present=True;assert c.run('produce',(SELF,SELF))==0 and count(c,'submit')==1
results.append('ordering:late_staging_arrival_allows_first_frame_without_reallocation')

c=Case(staging_present=False).init();c.run('connect_hook',(STATE,MESSAGE));c.u.mem_write(SELF,b'\x02')
for _ in range(35):assert c.run('produce',(SELF,SELF))==4
assert not count(c,'submit') and c.calls.count(('event',10))==1
assert c.run('failure_hook',(STATE,MESSAGE))==0 and count(c,'free')==0
results.append('ordering:missing_staging_deadline_unwinds_on_main_queue')
for name,params in [('too_small',{'staging':0x100000}),('overlap',{'staging_base':0x30000000}),('overflow',{'staging_base':0xfff00000})]:
 c=Case(**params).init();assert c.run('connect_hook',(STATE,MESSAGE))==0
 assert c.run('produce',(SELF,SELF))==4
 assert not count(c,'submit') and c.calls.count(('event',10))==1
 results.append('staging:'+name+'_rejected_before_dma_submission')

# Reproduce the hardware retry: old manager stopped with uncertain DMA,
# then Ready connect supplies a different manager while gadget is closed.
NEXT=SELF+0x5000
c=Case().init();c.run('connect_hook',(STATE,MESSAGE));c.run('produce',(SELF,SELF))
c.wait=1;assert c.run('stop_hook',(SELF,))==0
assert v1.word(c.u,c.syms['manager'])==0 and v1.word(c.u,c.syms['in_flight'])==1
assert not count(c,'free') and not count(c,'unmap')
results.append('restart:stop_detaches_manager_without_freeing_uncertain_source')
v1.put(c.u,SM+0x34,NEXT);c.u.mem_write(NEXT,b'\x01')
v1.put(c.u,NEXT+0x10,0x810);v1.put(c.u,NEXT+0x14,0x814);v1.put(c.u,NEXT+0x18,0x818)
calls_before=len(c.calls)
assert c.run('connect_hook',(STATE,MESSAGE))==0
assert not any(x[0] in ['wait','alloc','free','map','unmap','submit'] for x in c.calls[calls_before:])
assert v1.word(c.u,c.syms['manager'])==NEXT and count(c,'alloc')==1
assert c.run('start_hook',(NEXT,))==0
results.append('restart:new_manager_connects_without_waiting_on_closed_gadget')
sentinel=bytes([0xab])*(640*8*2)
c.u.mem_write(0x41000000+640*472*2,sentinel)
before=bytes(c.u.mem_read(0x41000000,614400))
assert c.run('produce',(NEXT,NEXT))==4
assert bytes(c.u.mem_read(0x41000000,614400))==before and count(c,'submit')==1
assert v1.word(c.u,c.syms['in_flight'])==1
results.append('restart:pinned_source_immutable_until_driver_completion')
c.wait=0;assert c.run('produce',(NEXT,NEXT))==0
assert count(c,'submit')==2 and bytes(c.u.mem_read(0x41000000+640*472*2,len(sentinel)))!=sentinel
assert count(c,'alloc')==1 and count(c,'map')==1 and not count(c,'free')
results.append('restart:completion_allows_reuse_without_reallocation')
# Repeated alternating manager lifetimes consume only one configured unit.
for n in range(8):
 old=NEXT if n%2==0 else SELF;new=SELF if n%2==0 else NEXT
 c.wait=1;assert c.run('finish_hook',(old,))==0
 v1.put(c.u,SM+0x34,new);assert c.run('connect_hook',(STATE,MESSAGE))==0
 c.wait=0;assert c.run('produce',(new,new))==0
assert count(c,'alloc')==1 and count(c,'map')==1 and not count(c,'free') and not count(c,'unmap')
results.append('restart:repeated_manager_recreation_keeps_allocation_bounded')
# A failed stop must not detach or allow a competing manager to bind.
c=Case(stop_error=True).init();c.run('connect_hook',(STATE,MESSAGE));c.run('produce',(SELF,SELF))
assert c.run('stop_hook',(SELF,))==4
v1.put(c.u,SM+0x34,NEXT);assert c.run('connect_hook',(STATE,MESSAGE))==4
assert v1.word(c.u,c.syms['manager'])==SELF and count(c,'alloc')==1
assert logs(c,'CONNECT_REJECTED')[-1][2]==33
results.append('restart:failed_stop_preserves_live_manager_exclusion')
# Stale/different manager cannot detach the current binding.
assert c.run('detach_source',(NEXT,))==33
assert v1.word(c.u,c.syms['manager'])==SELF and not count(c,'free')
results.append('restart:wrong_manager_cannot_detach_current_binding')

(OUT/'verification.json').write_text(json.dumps({'passed':len(results),'cases':results,'hardware_services_mocked':True},indent=2)+'\n')
print(json.dumps(results,indent=2))
