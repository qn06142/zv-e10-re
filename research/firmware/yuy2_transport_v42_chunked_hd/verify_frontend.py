"""Execute compiled ARM fail-closed frontend gates; no camera access."""
from pathlib import Path
import importlib.util,json
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
spec=importlib.util.spec_from_file_location('support',Path(__file__).parent/'recipe/verify_support.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
MODULE=Path('.local/outputs/hd-v42/build/yuy2_1080_v42chunk.so')
class Case:
 def __init__(self,version=b'yc42_chunk\n',self_pin=0):
  self.u=u=Uc(UC_ARCH_ARM,UC_MODE_ARM);self.handlers={};self.calls=[];self.version=version;self.self_pin=self_pin
  for a,n in [(0x10000000,0x10000),(m.STOP,4096),(0x60000000,0x20000)]:u.mem_map(a,n)
  self.s=m.load(u,MODULE,m.MB,self.imp);m.put(u,self.s['send_event'],self.imp('mock_event'));m.put(u,self.s['original_start'],self.imp('mock_start'));u.hook_add(UC_HOOK_CODE,self.hook)
 def imp(self,name):
  a=0x10000000+len(self.handlers)*4;self.handlers[a]=name;return a
 def hook(self,u,a,n,d):
  if a not in self.handlers:return
  name=self.handlers[a];self.calls.append(name);v=[u.reg_read(r) for r in m.R]
  if name=='open':r=10 if m.cstr(u,v[0])=='/sys/module/usbg_video/version' else -1
  elif name=='read':u.mem_write(v[1],self.version);r=len(self.version)
  elif name in ['close','snprintf','mock_event','mock_start']:r=0
  elif name=='memset':u.mem_write(v[0],bytes([v[1]&255])*v[2]);r=v[0]
  elif name=='memcmp':r=int(bytes(u.mem_read(v[0],v[2]))!=bytes(u.mem_read(v[1],v[2])))
  elif name=='dlopen':
   assert m.cstr(u,v[0])=='/usr/lib/yuy2_1080_v42chunk.so' and v[1]==6;r=self.self_pin
  else:raise AssertionError('unexpected side effect: '+name)
  u.reg_write(UC_ARM_REG_R0,r&0xffffffff);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 def set(self,n,v):m.put(self.u,self.s[n],v)
 def get(self,n):return m.word(self.u,self.s[n])
 def run(self,n,arg=0x1234):
  u=self.u;u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,m.STACK);u.reg_write(UC_ARM_REG_LR,m.STOP);u.reg_write(UC_ARM_REG_R0,arg)
  u.emu_start(self.s[n],m.STOP,count=20000)
  assert u.reg_read(UC_ARM_REG_PC)==m.STOP and u.reg_read(UC_ARM_REG_SP)==m.STACK
  return u.reg_read(UC_ARM_REG_R0)
passed=[]
c=Case();c.set('ready',1);assert c.run('yuy2_activate')==1 and not c.calls;passed.append('ready_activation_has_no_side_effects')
c=Case();c.set('activation_phase',1);assert c.run('yuy2_activate')==0 and not c.calls;passed.append('concurrent_activation_rejected')
c=Case();assert c.run('yuy2_activate')==0 and c.get('activation_phase')==3
assert c.calls.count('dlopen')==1;c.calls=[];assert c.run('yuy2_activate')==0 and not c.calls;passed.append('self_pin_failure_is_terminal_without_install')
c=Case();c.set('output_session_closed',1);assert c.run('start_hook')==4 and c.get('init_error')==41 and c.calls==['mock_event','snprintf','open'];passed.append('closed_session_rejected_before_procfs_or_sdk')
for ver in [b'',b'yuy2_640_v23\n',b'yc42_chunkBAD\n']:
 c=Case(version=ver);assert c.run('start_hook')==4 and c.get('init_error')==42;assert not any(x in c.calls for x in ['dlopen','dlsym','mmap']);passed.append('wrong_kernel_rejected_'+repr(ver))
c=Case();c.set('pixels',0x41000000);assert c.run('start_hook')==0 and c.get('manager')==0x1234;passed.append('matched_kernel_allows_retained_mapping_binding')
c=Case();c.set('pixels',0x41000000);assert c.run('detach_source')==0 and c.get('output_session_closed')==1
assert c.get('pixels')==0x41000000;passed.append('stop_before_host_capture_retains_mapping_and_closes_session')
out=dict(camera_access=False,compiled_ARM_executed=True,passed=passed,limitations=['External libc and loader calls mocked; no live DMA or camera lifecycle execution.'])
Path('.local/outputs/hd-v42/frontend-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
