"""Run the built Cortex-A5 snapshot-copy path; no Sony or DMA calls allowed."""
from pathlib import Path
import sys,struct,json
sys.path.insert(0,str(Path(__file__).parent/'recipe'))
from verify_support import load,put,word
from unicorn import *
from unicorn.arm_const import *
u=Uc(UC_ARCH_ARM,UC_MODE_ARM);imports={};by_address={};calls=[]
for a,n in [(0x10000000,0x10000),(0x41000000,0x200000),(0x50000000,4096),(0x60000000,0x20000)]:u.mem_map(a,n)
def imp(name):
 if name not in imports:imports[name]=0x10000000+4*len(imports);by_address[imports[name]]=name
 return imports[name]
s=load(u,Path('.local/outputs/vga-v36/build/yuy2_640_v36vga.so'),0x20000000,imp)
def hook(u,pc,size,_):
 if pc==s.get('memcpy'):
  calls.append('memcpy');return
 if pc not in by_address:return
 name=by_address[pc];calls.append(name)
 assert name=='memcpy',name
 a=[u.reg_read(r) for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2]]
 assert a[2]==614400;u.mem_write(a[0],bytes(u.mem_read(a[1],a[2])));u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
u.hook_add(UC_HOOK_CODE,hook)
for name,v in [('shared_captured',1),('shared_generation',1),('usb_physical',0x15000000),('usb_capacity',614400),('staging_physical',0x16000000),('staging_capacity',1843200),('shared_started',1)]:put(u,s[name],v)
pattern=bytes(range(256))*2400;u.mem_write(s['published'],pattern)
def run(out=0x41000000,physical=0x15000000):
 u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,0x60010000);u.reg_write(UC_ARM_REG_LR,0x50000000)
 for reg,v in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],[out,614400,0x41100000,physical]):u.reg_write(reg,v)
 put(u,0x60010000,0x16000000);put(u,0x60010004,1843200)
 u.emu_start(s['vga_resize_copy'],0x50000000,count=3000000)
 assert u.reg_read(UC_ARM_REG_PC)==0x50000000 and u.reg_read(UC_ARM_REG_SP)==0x60010000,(hex(u.reg_read(UC_ARM_REG_PC)),hex(u.reg_read(UC_ARM_REG_SP)),calls)
 return u.reg_read(UC_ARM_REG_R0)
assert run()==0 and bytes(u.mem_read(0x41000000,614400))==pattern
u.mem_write(s['published'],b'\xff'*614400)
for i in range(100):assert run()==0 and word(u,0x41100000)==1
assert bytes(u.mem_read(0x41000000,614400))==pattern and calls==['memcpy']
assert run(out=0x410a0000)==0xffffffff
assert run(physical=0x15001000)==0xffffffff
put(u,s['shared_stopping'],1);assert run()==0xffffffff
assert calls==['memcpy'] and word(u,s['shared_running'])==0
out=dict(camera_access=False,compiled_arm_instructions=True,successful_replay_calls=101,memcpy_calls=1,sony_ipc_calls=0,worker_restarts=0,checks=['first copy exact 614400 bytes','100 later polls do not write source','different pointer rejected','different physical address rejected','stop rejects further replay'],limitations=['Captured state is initialized by fixture; this does not emulate capture, DMA or hardware stability.'])
Path('.local/outputs/vga-v36/arm-snapshot-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))


