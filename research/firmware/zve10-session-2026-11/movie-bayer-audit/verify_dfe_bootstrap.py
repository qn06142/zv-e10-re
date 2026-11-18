"""Run archived dfe_app initialization; observe DMA requests without executing DMA."""
import argparse, hashlib, json, struct, tarfile
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *
p=argparse.ArgumentParser(description=__doc__);p.add_argument('repo',type=Path);a=p.parse_args()
with tarfile.open(a.repo/'dumps/trees/system.tgz') as t:
    d=t.extractfile('system/dfe_app.bin').read()
base=0xfe1ed000; stop=0x60000000; stack=0x50001000
u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
for addr,size in [(base,0x5000),(0xfc000000,0x18000),(0x40000000,0x1000),(0x50000000,0x2000),(stop,0x1000)]:u.mem_map(addr,size)
u.mem_write(base,d)
def word(addr):return struct.unpack('<I',u.mem_read(addr,4))[0]
def run(pc,*args):
    u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,stack);u.reg_write(UC_ARM_REG_LR,stop)
    for reg,value in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],args):u.reg_write(reg,value)
    u.emu_start(pc,stop,count=100000)
    assert u.reg_read(UC_ARM_REG_PC)==stop and u.reg_read(UC_ARM_REG_SP)==stack
    return u.reg_read(UC_ARM_REG_R0)
run(base+0x11)
assert word(0xfe1f0000)==0xfc036ff8 and word(0xfe1f0004)==0
assert bytes(u.mem_read(0xfe1f0800,0x800))==bytes(0x800)
requests=[]
def hook(u,pc,size,_):
    if pc==base+0x5a0:
        ptr=u.reg_read(UC_ARM_REG_R0)
        first,second,n=struct.unpack('<3I',u.mem_read(ptr,12))
        requests.append(dict(operand0=hex(first),operand1=hex(second),length=n))
        u.reg_write(UC_ARM_REG_R0,0);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
u.hook_add(UC_HOOK_CODE,hook)
assert run(base+0xa1,0x40000000)==0
assert requests==[
    dict(operand0='0x1017fd0',operand1='0x1010000',length=0x7fd0),
    dict(operand0='0x1017fd0',operand1='0x1030000',length=0x10000)], requests
assert word(0x40000000)==0xfe1f0020
assert [word(0xfc017fd0+i*4) for i in range(12)]==[0]*12
print(json.dumps(dict(image='system.tgz:system/dfe_app.bin',size=len(d),
    sha256=hashlib.sha256(d).hexdigest(),base=hex(base),
    native_startup='0xfe1ed010',native_initializer='0xfe1ed0a0',
    intercepted=['DMA routine 0xfe1ed5a0, returns fixture status 0'],
    startup_relocation_verified=True,zero_padding_words_verified=12,
    dma_requests=requests, address_translation='native 32-bit addition of 0x05000000',
    operand_direction_or_fill_mode_assigned=False,
    hardware_transfer_executed=False,pixels_emulated=False),indent=2))
