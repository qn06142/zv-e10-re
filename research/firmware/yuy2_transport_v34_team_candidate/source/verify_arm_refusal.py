"""Execute compiled ARM candidate-rejection path; SDK call mocked, no camera."""
from pathlib import Path
import importlib.util,struct,json
from unicorn import *
from unicorn.arm_const import *
spec=importlib.util.spec_from_file_location('support',Path(__file__).parent/'recipe/verify_support.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
rows=[]
for name,change,rc,optional in [('exact_rejection',None,0,1),('required_destination_rejection',None,0,0),('transport_failure',None,1,1),('wrong_command',(0,0x8005),0,1),('wrong_handle',(4,0x1756),0,1),('wrong_queue',(6,0x611b),0,1),('wrong_native_error',(10,0xfdfb),0,1),('wrong_type',(12,0x1234),0,1),('unexpected_address',(16,0x1234),0,1)]:
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);handlers={};tags=[];sdk_calls=[]
 for p,n in [(0x10000000,0x10000),(0x40000000,0x10000),(m.STOP,4096),(0x60000000,0x20000)]:u.mem_map(p,n)
 def imp(n):
  a=0x10000000+len(handlers)*4;handlers[a]=n;return a
 sy=m.load(u,Path('.local/outputs/vga-v34/build/yuy2_640_v34vga.so'),m.MB,imp)
 share=imp('SDK_SHARE');m.put(u,sy['sdk']+2*4,share);m.put(u,sy['dmm']+4,0x0035611a)
 raw=bytearray(struct.pack('<6I',0xffff8002,0x611a1755,0xffff0000,0xe0b00,0,0))
 if change:
  off,value=change;struct.pack_into('<I' if off>=12 else '<H',raw,off,value)
 def hook(u,a,size,data):
  if a not in handlers:return
  n=handlers[a];v=[u.reg_read(r) for r in m.R]
  if n=='SDK_SHARE':sdk_calls.append(n);u.mem_write(v[1],bytes(raw));result=rc
  elif n=='snprintf':tags.append(m.cstr(u,v[3]));result=0
  elif n=='memset':u.mem_write(v[0],bytes([v[1]&255])*v[2]);result=v[0]
  elif n=='memcpy':u.mem_write(v[0],bytes(u.mem_read(v[1],v[2])));result=v[0]
  else:raise AssertionError(n)
  u.reg_write(UC_ARM_REG_R0,result);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 u.hook_add(UC_HOOK_CODE,hook)
 for r,v in [(UC_ARM_REG_CPSR,0x10),(UC_ARM_REG_SP,m.STACK),(UC_ARM_REG_LR,m.STOP),(m.R[0],0x40000000),(m.R[1],0x1755),(m.R[2],0xe0b00),(m.R[3],optional)]:u.reg_write(r,v)
 u.emu_start(sy['take_impl'],m.STOP,count=100000);assert u.reg_read(UC_ARM_REG_PC)==m.STOP
 result=u.reg_read(m.R[0]);fault=m.word(u,sy['shared_fault']);assert sdk_calls==['SDK_SHARE']
 if name=='exact_rejection':assert result==1 and not fault and bytes(u.mem_read(0x40000000,36))==bytes(36) and 'SOURCE_SHARE_DECLINED' in tags
 else:assert result==0xffffffff and fault==1 and m.word(u,0x40000000+16)==1 and 'SHARE_FAILED' in tags
 rows.append(dict(case=name,result=result,fault=fault,markers=tags))
out=dict(passed=len(rows),compiled_ARM_executed=True,hardware_boundaries_mocked=True,camera_access=False,cases=rows)
Path('.local/outputs/vga-v34/arm-refusal-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
