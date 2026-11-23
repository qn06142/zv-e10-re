"""Execute resident image and its exception vectors; MMIO/CP15 effects are modeled."""
import json,struct,sys
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_PC,UC_ARM_REG_SP,UC_ARM_REG_CPSR
from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM


def verify(blob,display=False):
    reports=[]
    for base in (0x100000,0x510000):
        for high in (0,0x2000):
            cpu=Uc(UC_ARCH_ARM,UC_MODE_ARM)
            info,stack,gpio,misc,wdt=0x2000000,0x2100000,0xf2910000,0xf2915000,0xf2402000
            for address,size in ((base,4096),(info,4096),(stack,8192),(gpio,0x3000),(misc,4096),(wdt,4096)):
                cpu.mem_map(address,size)
            if display:
                cpu.mem_map(0xf3445000,4096);cpu.mem_write(0xf3445108,struct.pack('<I',0x84012345))
            cpu.mem_write(base,blob);cpu.mem_write(info,struct.pack('<7I',0x5a564231,gpio,misc+0x44,3,0,0,0))
            cpu.reg_write(UC_ARM_REG_CPSR,0x13);cpu.reg_write(UC_ARM_REG_R0,info);cpu.reg_write(UC_ARM_REG_R1,stack+8192)
            instructions={base+i.address:i for i in Cs(CS_ARCH_ARM,CS_MODE_ARM).disasm(blob,0)}
            state={'sctlr':0x10c5187d|high,'vbar':None};writes=[];heartbeats=[];display_values=[]
            def code(cpu,address,size,_):
                assert base<=address<base+len(blob),'Left owned image'
                ins=instructions[address]
                if ins.mnemonic=='mrc':
                    assert bytes(ins.bytes)==bytes.fromhex('103f11ee')
                    cpu.reg_write(UC_ARM_REG_R3,state['sctlr']);cpu.reg_write(UC_ARM_REG_PC,address+4)
                elif ins.mnemonic=='mcr':
                    if bytes(ins.bytes)==bytes.fromhex('102f0cee'):state['vbar']=cpu.reg_read(UC_ARM_REG_R2)
                    else:
                        assert bytes(ins.bytes)==bytes.fromhex('103f01ee')
                        state['sctlr']=cpu.reg_read(UC_ARM_REG_R3)
                    cpu.reg_write(UC_ARM_REG_PC,address+4)
                assert ins.mnemonic not in ('svc','swi')
            def write(cpu,access,address,size,value,_):
                assert size==4
                if display and address==0xf3445108:
                    assert value==([0x87eb8080,0x87108080][len(display_values)%2])
                    display_values.append(value)
                elif address==info+16:assert value==0x52554e32
                elif address==info+20:
                    assert value==len(heartbeats)+1;heartbeats.append(value)
                    if value==5:cpu.emu_stop()
                elif address==info+24:assert value==0x46414c54
                else:
                    allowed={misc+0x48:0x10,wdt:0,wdt+4:0x11}
                    allowed.update({gpio+o:1 for o in (4,0x28,0x44,0x48,0x2024,0x2034,0x2044)})
                    assert address in allowed and value==allowed[address],(hex(address),hex(value))
                    writes.append((address,value))
            cpu.hook_add(UC_HOOK_CODE,code);cpu.hook_add(UC_HOOK_MEM_WRITE,write)
            cpu.emu_start(base,base+len(blob),count=10000)
            assert heartbeats==[1,2,3,4,5]
            assert len(display_values)==(10 if display else 0)
            assert state=={'sctlr':0x10c5187d,'vbar':base}
            assert writes[:3]==[(misc+0x48,0x10),(wdt,0),(wdt+4,0x11)]
            assert sum(a==gpio+0x48 for a,v in writes)==5
            assert sum(a==gpio+0x44 for a,v in writes)==6
            assert cpu.reg_read(UC_ARM_REG_SP)==stack+8192
            assert cpu.reg_read(UC_ARM_REG_CPSR)&0xdf==0xd3
            # Explicitly dispatch all private fault vectors; no exception stack or Linux handler.
            for offset in range(4,32,4):
                cpu.mem_write(info+24,b'\0'*4)
                cpu.emu_start(base+offset,base+len(blob),count=50)
                assert struct.unpack('<I',cpu.mem_read(info+24,4))[0]==0x46414c54
            reports.append({'base':hex(base),'initial_high_vectors':bool(high),'heartbeat_cycles':5,'private_fault_vectors_tested':7,'no_reset_request':True,'display_colour_writes':len(display_values)})
    return {'status':'resident-ARM-runtime-verified','cases':reports,'limits':'CP15 and MMIO effects modeled; Linux shutdown, RTOS ownership and hardware timing not emulated'}


if __name__=='__main__':print(json.dumps(verify(Path(sys.argv[1]).read_bytes(),display='--display' in sys.argv[2:])))
