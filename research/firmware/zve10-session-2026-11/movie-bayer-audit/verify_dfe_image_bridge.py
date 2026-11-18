"""Verify embedded image provenance and native ARM script IRQ processing.

MMIO and command operands are RAM fixtures; no cross-CPU bus model is assumed.
"""
import argparse,hashlib,json,struct,sys
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM
from unicorn.arm_const import *
p=argparse.ArgumentParser(description=__doc__);p.add_argument('repo',type=Path);a=p.parse_args()
sys.path.insert(0,str(a.repo/'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness,MEM
from rtos import DATA,BASE
d=(a.repo/'dumps/firmware/dfe_dat.bin').read_bytes()
h=Harness()
assert h.run(0x639dfb38,MEM,MEM+4)==1
ptr,size=h.word(MEM),h.word(MEM+4)
assert ptr==0x64560700 and size==65536
assert bytes(h.u.mem_read(ptr,size))==d
u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
u.mem_map(0x01000000,0xa0000);u.mem_write(0x01000000,d)
for addr,n in [(0x40000000,0x10000),(0x50000000,0x2000),(0x60000000,0x1000)]:u.mem_map(addr,n)
def put(addr,value):u.mem_write(addr,struct.pack('<I',value))
def word(addr):return struct.unpack('<I',u.mem_read(addr,4))[0]
context=0x01036d00;irq=0x01080104;target=0x40001000
rows=[]
for event in [8,16]:
    for first,last in [(0,0),(0,1),(0,3),(1,3),(0,61),(0,62),(3,1)]:
        u.mem_write(context,bytes(0x400));u.mem_write(target,bytes(0x100))
        put(context+4,first);put(context+8,last)
        for i in range(62):
            put(context+0x10+i*12,1)
            put(context+0x14+i*12,target+i*4)
            put(context+0x18+i*12,0x12340000+i)
        put(irq,event)
        u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,0x50001000)
        u.reg_write(UC_ARM_REG_LR,0x60000000)
        u.emu_start(0x0100030c,0x60000000,count=20000)
        assert u.reg_read(UC_ARM_REG_PC)==0x60000000
        assert u.reg_read(UC_ARM_REG_SP)==0x50001000
        valid=first<=last<=61
        expected=list(range(first if event==16 else 0,last if event==16 else first)) if valid else []
        actual=[i for i in range(62) if word(target+4*i)]
        assert actual==expected,(event,first,last,actual,expected)
        header=list(u.mem_read(context,4))
        assert header[0]==1 and header[1]==2 and header[3]==1
        assert word(irq)==event
        rows.append(dict(event=event,first=first,last=last,header_bytes=header,written_indices=actual))
print(json.dumps(dict(native_embedded_getter='0x639dfb38',embedded_address=hex(ptr),size=size,
    md5=hashlib.md5(d).hexdigest(),byte_for_byte_equal=True,irq_cases=len(rows),
    native_irq_handler='0x0100030c',script_context=hex(context),irq_register=hex(irq),mocks=[],
    fixtures=['IRQ register','shared script header and records','RAM destinations'],
    local_to_host_address_translation_proved=False,pixels_or_dma_emulated=False,rows=rows),indent=2))
