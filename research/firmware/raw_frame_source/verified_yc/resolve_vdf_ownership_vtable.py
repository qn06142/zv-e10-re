from pathlib import Path
import struct
from unicorn import *
from unicorn.arm_const import *
b=Path(r'D:/02_Development_And_Projects/pmca-re/dumps/firmware/av-cam.bin').read_bytes();u=Uc(UC_ARCH_ARM,UC_MODE_THUMB);base=0x635c6000;u.mem_map(base,(len(b)+4095)&~4095);u.mem_write(base,b);u.mem_map(0x10000000,0x10000)
for f in [0x63748990,0x637489b0]:
 u.reg_write(UC_ARM_REG_SP,0x1000f000);u.reg_write(UC_ARM_REG_LR,0x10001000);u.reg_write(UC_ARM_REG_R0,0x10000000);u.reg_write(UC_ARM_REG_R1,0x10000100);u.emu_start(f|1,0x10001000,count=1000)
 v=struct.unpack('<I',u.mem_read(0x10000000,4))[0];print(hex(f),'vtable',hex(v),[hex(x) for x in struct.unpack('<8I',u.mem_read(v,32))])
