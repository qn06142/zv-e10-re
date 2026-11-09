"""Native DFE ARM versus bootstrap Thumb DMA checks with explicit register fixtures.

No DMA/pixels are simulated. A bounded instruction run detects software polling
that does not return; it is not a hardware timeout model.
"""
import argparse,json,struct,tarfile
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
p=argparse.ArgumentParser(description=__doc__);p.add_argument('repo',type=Path);a=p.parse_args()
core=(a.repo/'dumps/firmware/dfe_dat.bin').read_bytes()
with tarfile.open(a.repo/'dumps/trees/system.tgz') as t:app=t.extractfile('system/dfe_app.bin').read()
u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
for addr,size in [(0x01000000,0xa0000),(0xfe1ed000,0x1000),
                  (0xfc01d000,0x1000),(0x40000000,0x1000),
                  (0x50000000,0x2000),(0x60000000,0x1000)]:u.mem_map(addr,size)
u.mem_write(0x01000000,core);u.mem_write(0xfe1ed000,app)
def put(addr,value):u.mem_write(addr,struct.pack('<I',value&0xffffffff))
def word(addr):return struct.unpack('<I',u.mem_read(addr,4))[0]
writes=[];fixture_addr=None;fixture_value=0;reads=0
def onwrite(u,access,addr,size,value,_):
    if 0x0101d000<=addr<0x0101d100 or 0xfc01d000<=addr<0xfc01d100:
        writes.append(dict(address=hex(addr),size=size,value=hex(value)))
def onread(u,access,addr,size,value,_):
    global reads
    if addr==fixture_addr:
        reads+=1;put(addr,fixture_value)
u.hook_add(UC_HOOK_MEM_READ,onread);u.hook_add(UC_HOOK_MEM_WRITE,onwrite)
def run(pc,*args):
    u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,0x50001000)
    u.reg_write(UC_ARM_REG_LR,0x60000000)
    for reg,v in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],args):u.reg_write(reg,v)
    u.emu_start(pc,0x60000000,count=2000)
    returned=u.reg_read(UC_ARM_REG_PC)==0x60000000
    if returned:assert u.reg_read(UC_ARM_REG_SP)==0x50001000
    return returned,u.reg_read(UC_ARM_REG_R0)
rows=[]
for channel in [0,1,2,3]:
    for length in [0,1,2,3,4,5,7,8,64,51680]:
        fixture_addr=None;writes.clear()
        put(0x0101d000+16*channel+0x10,0)
        assert run(0x01001458,0x20000000,0x21000000,length,channel)[0]
        control=word(0x0101d000+16*channel+0x10)
        assert control==(((length>>2)-1)|0xa0800000)&0xffffffff
        assert word(0x0101d000+16*channel+0x18)==0x20000000
        assert word(0x0101d000+16*channel+0x1c)==0x21000000
        core_writes=len(writes)
        writes.clear();reads=0
        put(0x40000000,0x20000000);put(0x40000004,0x21000000);put(0x40000008,length)
        put(0xfc01d000+16*channel+0x10,0)
        fixture_addr=0xfc01d000+16*channel+0x14;fixture_value=0x50000
        returned,result=run(0xfe1ed5ad,channel,0x40000000,0)
        assert returned
        valid=length>0 and length%4==0
        assert result==(0 if valid else 0x10)
        assert bool(writes)==valid
        rows.append(dict(channel=channel,length=length,core_control=hex(control),
                         core_register_writes=core_writes,bootstrap_return=result,
                         bootstrap_register_writes=len(writes)))
waits=[]
for status in [0,0x10000,0x20000,0x30000,0x40000,0x50000,0x60000,0x70000,0x80000,0x100000,0x180000]:
    writes.clear();reads=0
    fixture_addr=0x0101d014;fixture_value=status
    returned,result=run(0x01001498,0)
    assert returned==bool(status&0x70000)
    if returned:assert result==status
    core_reads=reads;core_poll_writes=len(writes)
    writes.clear();reads=0
    fixture_addr=0xfc01d014;fixture_value=status
    put(0xfc01d010,0);put(0x40000008,4)
    app_returned,app_result=run(0xfe1ed5ad,0,0x40000000,0)
    if status==0:assert not app_returned
    elif status&0x180000:assert app_returned and app_result==8
    else:assert app_returned and app_result=={1:1,2:2,3:3,4:4,5:0,6:255,7:7}[(status>>16)&7], (hex(status),app_returned,app_result)
    waits.append(dict(status=hex(status),core_returned=returned,
                      core_return=hex(result) if returned else None,
                      core_status_reads=core_reads,core_poll_writes=core_poll_writes,
                      bootstrap_returned=app_returned,
                      bootstrap_return=app_result if app_returned else None))
print(json.dumps(dict(start_cases=len(rows),status_cases=len(waits),
    native_core_start='0x01001458',native_core_wait='0x01001498',
    native_bootstrap_dma='0xfe1ed5ac',function_mocks=[],
    fixtures=['RAM operands, not copied','DMA register initial values','fixed DMA status on reads'],
    instruction_budget_per_call=2000,hardware_timeout_modeled=False,
    dma_executed=False,pixels_emulated=False,start_rows=rows,status_rows=waits),indent=2))
