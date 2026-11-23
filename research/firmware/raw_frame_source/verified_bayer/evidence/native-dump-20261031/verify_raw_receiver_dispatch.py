from pathlib import Path
import sys,json,struct
sys.path.insert(0,str(Path('.local/work/hd-v42/recipe').resolve()))
import verify_support as m
from unicorn import *
from unicorn.arm_const import *
P=Path('D:/02_Development_And_Projects/pmca-re/.local/dumps/camera_2025/usr/usr/lib/CameraOnDemandSaver.so');rows=[]
for mode,result in [(0,1),(0,0),(8,1),(6,1),(32,1),(7,0)]:
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);handlers={};events=[];B=0x20000000;M=0x40000000
 def imp(n):
  a=0x10000000+len(handlers)*4;handlers[a]=n;return a
 u.mem_map(0x10000000,0x10000);s=m.load(u,P,B,imp);u.mem_map(M,0x10000);u.mem_map(m.STOP,4096);u.mem_map(m.STACK-0x10000,0x20000)
 msg=M+0x1004;m.put(u,msg-4,0x1234);u.mem_write(msg,struct.pack('<HHII4BII',1,0x701,0x20000000,4096,5,mode,0,0,0,0))
 def ret(v):u.reg_write(UC_ARM_REG_R0,v&0xffffffff);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 def hook(u,pc,size,_):
  if pc in [B+0x1514,B+0x1534,B+0x1556]:ret(0);return
  if pc not in handlers:return
  n=handlers[pc];a=[u.reg_read(r) for r in m.R]
  if n=='osal_rcv_msg_tmo':m.put(u,a[1],msg);ret(0)
  elif 'fsys_write' in n or 'linux_write' in n:events.append(dict(write=n,result=result));ret(result)
  elif '7snd_msg' in n:events.append(dict(reply_arguments=a));ret(0)
  elif n=='osal_free_msg':events.append(dict(free=True));u.reg_write(UC_ARM_REG_PC,m.STOP)
  else:raise AssertionError(n)
 u.hook_add(UC_HOOK_CODE,hook);u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,m.STACK);u.reg_write(UC_ARM_REG_R0,M);u.reg_write(UC_ARM_REG_R1,0x12802f1);u.reg_write(UC_ARM_REG_LR,m.STOP)
 u.emu_start(B+0x1c8d,m.STOP,count=20000)
 reply=next(e['reply_arguments'] for e in events if 'reply_arguments'in e);assert reply[1:]==[0x12802f1,0x1234,result]
 assert events[-1]==dict(free=True)
 rows.append(dict(mode=mode,writer_result=result,events=events))
Path('.local/outputs/sensor-bayer-20261031/receiver-dispatch-tests.json').write_text(json.dumps(dict(original_instructions=True,camera_access=False,cases=rows,limitations='Writer methods and OS message calls mocked; verifies dispatch and ordering, not actual storage.'),indent=2));print('Passed six native receiver dispatch/reply ordering cases')
