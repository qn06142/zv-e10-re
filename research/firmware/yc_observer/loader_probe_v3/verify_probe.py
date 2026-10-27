from pathlib import Path
import importlib.util,json
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
REPO=Path('D:/02_Development_And_Projects/pmca-re');OUT=Path('outputs/yc-retest-20261024/candidate')
spec=importlib.util.spec_from_file_location('support',REPO/'research/firmware/yuy2_transport_v25/verify_support.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
results=[]
for case in ['success','open_failure','short_write']:
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);handlers={};calls=[]
 for a,n in [(0x10000000,4096),(m.STOP,4096),(0x60000000,0x20000)]:u.mem_map(a,n)
 def imp(name):
  assert name in ['open','write','close'],name
  at=0x10000000+len(handlers)*4;handlers[at]=name;return at
 syms=m.load(u,OUT/'yc_probe_v3.so',0x20000000,imp)
 def hook(u,a,n,d):
  if a not in handlers:return
  name=handlers[a];r=[u.reg_read(x) for x in m.R];calls.append(name)
  assert u.reg_read(UC_ARM_REG_SP)%8==0
  if name=='open':
   assert m.cstr(u,r[0])=='/log/yc_observer/runtime-v3.log' and r[1:3]==[0x441,0o644]
   value=-1 if case=='open_failure' else 9
  elif name=='write':
   assert r[0]==9 and bytes(u.mem_read(r[1],r[2]))==b'YC_V3_LOADER_ACTIVATION_OK\n'
   value=r[2]-1 if case=='short_write' else r[2]
  else:assert r[0]==9;value=0
  u.reg_write(UC_ARM_REG_R0,value&0xffffffff);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 u.hook_add(UC_HOOK_CODE,hook)
 def run():
  u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,m.STACK);u.reg_write(UC_ARM_REG_LR,m.STOP);u.emu_start(syms['yc_observer_activate'],m.STOP,count=10000);assert u.reg_read(UC_ARM_REG_PC)==m.STOP and u.reg_read(UC_ARM_REG_SP)==m.STACK;return u.reg_read(UC_ARM_REG_R0)
 assert run()==(case=='success')
 if case=='success':
  before=calls[:];assert run()==1 and calls==before
 assert calls==(['open'] if case=='open_failure' else ['open','write','close'])
 results.append(case)
(OUT/'probe-verification.json').write_text(json.dumps({'passed':results,'only_imports':['open','write','close'],'camera_access':False},indent=2));print('Probe checks passed:',results)
