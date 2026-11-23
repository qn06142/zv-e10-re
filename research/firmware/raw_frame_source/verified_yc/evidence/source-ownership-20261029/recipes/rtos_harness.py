"""Execute original RTOS helpers; intercept only memory and DMM transport."""
import struct,json,hashlib
from pathlib import Path
from unicorn import *
from unicorn.arm_const import *
from rtos import DATA,BASE,word as fw_word
MEM=0x40000000;STACK=0x50010000;STOP=0x60000000
class Harness:
 def __init__(self):
  self.u=Uc(UC_ARCH_ARM,UC_MODE_THUMB);u=self.u
  u.mem_map(BASE,(len(DATA)+4095)&~4095);u.mem_write(BASE,DATA)
  for a,n in [(MEM,0x400000),(STACK-0x10000,0x20000),(STOP,4096)]:u.mem_map(a,n)
  self.callbacks={};self.calls=[];self.u.hook_add(UC_HOOK_CODE,self.hook)
  self.u.hook_add(UC_HOOK_MEM_INVALID,self.invalid)
 def invalid(self,u,access,address,size,value,data):
  raise AssertionError(dict(invalid_address=hex(address),pc=hex(u.reg_read(UC_ARM_REG_PC)),lr=hex(u.reg_read(UC_ARM_REG_LR)),last_calls=self.calls[-15:]))
 def word(self,a):return struct.unpack('<I',self.u.mem_read(a,4))[0]
 def put(self,a,v):self.u.mem_write(a,struct.pack('<I',v&0xffffffff))
 def ret(self,v=0):self.u.reg_write(UC_ARM_REG_R0,v&0xffffffff);self.u.reg_write(UC_ARM_REG_PC,self.u.reg_read(UC_ARM_REG_LR))
 def hook(self,u,pc,size,_):
  if size==4 and bytes(u.mem_read(pc,2))[1]&0xf8==0xf0:self.calls.append(hex(pc))
  a=[u.reg_read(r) for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]]
  if pc==0x63ae8ad0:u.mem_write(a[0],bytes([a[1]&255])*a[2]);self.ret(a[0])
  elif pc==0x63ae83ec:u.mem_write(a[0],bytes(u.mem_read(a[1],a[2])));self.ret(a[0])
  elif pc in self.callbacks:self.callbacks[pc](a)
 def run(self,pc,*args,balanced=True):
  u=self.u;u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,STACK);u.reg_write(UC_ARM_REG_LR,STOP|1)
  regs=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]
  for i,v in enumerate(args):
   if i<4:u.reg_write(regs[i],v)
   else:self.put(STACK+(i-4)*4,v)
  try:u.emu_start(pc|1,STOP,count=200000)
  except Exception as error:raise AssertionError(dict(error=str(error),pc=hex(u.reg_read(UC_ARM_REG_PC)),lr=hex(u.reg_read(UC_ARM_REG_LR)),last_calls=self.calls[-15:])) from error
  assert u.reg_read(UC_ARM_REG_PC)==STOP,hex(u.reg_read(UC_ARM_REG_PC));assert not balanced or u.reg_read(UC_ARM_REG_SP)==STACK
  return u.reg_read(UC_ARM_REG_R0)
