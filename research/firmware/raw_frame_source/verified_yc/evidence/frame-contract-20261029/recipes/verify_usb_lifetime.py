"""Execute selected original kernel paths; no DMA, UDC or scheduler is emulated."""
from pathlib import Path
import io,struct,json
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
P=Path('D:/02_Development_And_Projects/pmca-re/.local/dumps/camera_2025/usr/usr/kmod/usbg_video.ko')
e=ELFFile(io.BytesIO(P.read_bytes()));code=e.get_section_by_name('.text').data()
B=0x100000;S=0x200000;D=0x210000;O=0x220000;ST=0x50010000;TASK=0x50020000;STOP=0x60000000
def put(u,a,v):u.mem_write(a,struct.pack('<I',v&0xffffffff))
def word(u,a):return struct.unpack('<I',u.mem_read(a,4))[0]
def machine():
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
 for a,n in [(B,0x10000),(S,0x10000),(D,0x10000),(O,0x10000),(ST,0x20000),(STOP,0x1000)]:u.mem_map(a,n)
 u.mem_write(B,code);u.reg_write(UC_ARM_REG_SP,ST+0x7f00);u.reg_write(UC_ARM_REG_LR,STOP)
 put(u,B+0x23c8,S);put(u,B+0x10dc,S);put(u,B+0x10e4,D);put(u,B+0x10e8,S+0x28)
 put(u,ST+0x600c,TASK);u.reg_write(UC_ARM_REG_FP,ST+0x7f80)
 return u
cases=[]
for a,b in [(0,0),(1,0),(0,1),(1,1)]:
 u=machine();u.mem_write(S+0x10,bytes([a,b]));u.reg_write(UC_ARM_REG_R1,0xf002)
 def hook(u,pc,size,user):
  if pc in [B+v for v in [0x22b4,0x22c0,0x22ec,0x22f8]]:
   u.reg_write(UC_ARM_REG_R0,O);u.reg_write(UC_ARM_REG_PC,pc+4)
 u.hook_add(UC_HOOK_CODE,hook);u.emu_start(B+0x1e10,STOP,count=1000)
 assert u.reg_read(UC_ARM_REG_PC)==STOP
 rc=u.reg_read(UC_ARM_REG_R0);assert rc==(0xfffffff0 if a and b else 0)
 cases.append(dict(slot_flags=[a,b],ioctl='0xf002',return_signed=rc if rc<0x80000000 else rc-0x100000000))
for complete in [False,True]:
 u=machine();put(u,D,int(complete));u.reg_write(UC_ARM_REG_R5,D);u.reg_write(UC_ARM_REG_R7,614400)
 visits=[]
 def hook(u,pc,size,user):
  visits.append(pc-B)
  if pc in [B+v for v in [0xf90,0xfbc,0xff0,0x1018,0xfd4,0x1048,0x1050,0x105c,0x10b4,0x10bc]]:
   # Scheduler expiration is controlled, not an actual DMA timeout measurement.
   u.reg_write(UC_ARM_REG_R0,O if pc in [B+0x1050,B+0x105c,B+0x10b4] else 0);u.reg_write(UC_ARM_REG_PC,pc+4)
  elif pc==B+0x10d0:u.emu_stop()
 u.hook_add(UC_HOOK_CODE,hook)
 try:u.emu_start(B+0xf88,STOP,count=1000)
 except Exception:
  print('PC',hex(u.reg_read(UC_ARM_REG_PC)),'r4',hex(u.reg_read(UC_ARM_REG_R4)),'visits',visits[-15:]);raise
 assert u.reg_read(UC_ARM_REG_PC)==B+0x10d0
 assert u.reg_read(UC_ARM_REG_R0)==0 and bytes(u.mem_read(S+0x10,2))==b'\1\0'
 assert (0x1048 in visits)==(not complete)
 cases.append(dict(fragment='0xf88..0x10d0',dma_done=complete,scheduler_expiration_mocked=True,timeout_log_called=0x1048 in visits,return_value=0,queued_slot_bytes=word(u,S+0x1c),slot_flags=list(u.mem_read(S+0x10,2))))
u=machine();put(u,O+0xac,D+0x100);put(u,O,O+0x800);put(u,O+4,0x75000000);put(u,O+0xb0,0x42)
u.reg_write(UC_ARM_REG_R5,0x12340000);put(u,ST+0x7f80-0x2c,614400)
def prefix(u,pc,size,_):
 if pc==B+0xf70:u.emu_stop();return
 if pc in [B+v for v in [0xe7c,0xe94,0xea0,0xee0]]:u.reg_write(UC_ARM_REG_R0,O);u.reg_write(UC_ARM_REG_PC,pc+4)
 elif pc==B+0xee8:u.reg_write(UC_ARM_REG_PC,pc+4)
 elif pc in [B+0xe78,B+0xf3c]:
  a=[u.reg_read(r) for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2]]
  u.mem_write(a[0],bytes(a[2]) if pc==B+0xe78 else bytes(u.mem_read(a[1],a[2])));u.reg_write(UC_ARM_REG_PC,pc+4)
u.hook_add(UC_HOOK_CODE,prefix);u.emu_start(B+0xe68,STOP,count=500)
assert u.reg_read(UC_ARM_REG_PC)==B+0xf70
desc=list(struct.unpack('<3I',u.mem_read(D+0x100,12)));assert desc==[614400,0x12340000,0x7500000c]
cases.append(dict(fragment='0xe68..0xf70 before DMA call',dma_record_words=[hex(v) for v in desc],meaning=['pixel byte count','source physical address','internal USB staging physical address + 12-byte header'],dma_channel_argument=hex(u.reg_read(UC_ARM_REG_R0))))
out=dict(camera_access=False,original_arm_instructions=True,cases=cases,limitations=['Relocated only literals used by selected paths; not a complete kernel loader.','Get-this, memory helpers, locks, timeout expiration and logging mocked. No DMA/UDC execution or cancellation proof.','F002 success means a staging slot is available, not proof of successful source DMA. A simulated missing DMA completion still reaches a zero return from submit.'])
Path('.local/outputs/yc-frame-contract-20261029/usb-buffer-lifetime.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))




