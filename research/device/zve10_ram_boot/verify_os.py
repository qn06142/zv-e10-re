"""Execute the minimal ARM image with modeled GPIO/reset registers."""
import json
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_SP,UC_ARM_REG_CPSR
from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM
import struct


def verify(blob):
    instructions=list(Cs(CS_ARCH_ARM,CS_MODE_ARM).disasm(blob,0))
    assert len(instructions)*4==len(blob)
    assert not any(i.mnemonic in ('svc','swi','mcr','mrc','bl','blx') for i in instructions)
    results=[]
    for base in (0x100000,0x510000):
        cpu=Uc(UC_ARCH_ARM,UC_MODE_ARM)
        info,stack,gpio,reset=0x2000000,0x2100000,0x2200000,0x2300000
        for a,size in ((base,0x1000),(info,0x1000),(stack,0x2000),(gpio,0x3000),(reset,0x1000)):
            cpu.mem_map(a,size)
        cpu.mem_write(base,blob)
        cpu.mem_write(info,struct.pack('<5I',0x5a564231,gpio,reset+0x44,3,0))
        cpu.reg_write(UC_ARM_REG_CPSR,0x13)
        cpu.reg_write(UC_ARM_REG_R0,info);cpu.reg_write(UC_ARM_REG_R1,stack+0x2000)
        writes=[];reset_seen=[]
        def write(cpu,access,address,size,value,_):
            assert size==4
            if address==info+16:assert value==0x454e5452
            elif gpio<=address<gpio+0x3000:
                assert address-gpio in (4,0x28,0x44,0x48,0x2024,0x2034,0x2044)
                assert value==1
                writes.append(address-gpio)
            elif address==reset+0x44:
                assert value==0x11
                reset_seen.append(True)
                cpu.emu_stop()
            else:raise AssertionError(hex(address))
        cpu.hook_add(UC_HOOK_MEM_WRITE,write)
        cpu.emu_start(base,base+len(blob),count=2000)
        assert cpu.reg_read(UC_ARM_REG_SP)==stack+0x2000
        assert cpu.reg_read(UC_ARM_REG_CPSR)&0xdf==0xd3
        assert len(reset_seen)==1
        assert writes.count(0x48)==3 and writes.count(0x44)==4
        assert struct.unpack('<I',cpu.mem_read(info+16,4))[0]==0x454e5452
        results.append({'entry_va':hex(base),'gpio_writes':writes,'three_pulses':True,
                        'force_reset_value':'0x11','private_stack_and_masked_interrupts':True})
    return {'status':'offline-ARM-image-verified','tests':results,
            'limits':'GPIO/reset effects and delay timing are modeled; Linux shutdown/SMP stop are not emulated'}


if __name__=='__main__':
    import sys
    result=verify(Path(sys.argv[1]).read_bytes())
    print(json.dumps(result))
