from pathlib import Path
import json
from unicorn import *
from unicorn.arm_const import *
O=Path('outputs/yc-retest-20261024/candidate');SB=0xa661000;DL=0x40ba000
regs=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]
results=[]
for fail in ['none','dlopen','dlsym','activation']:
    u=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
    for a,n in [(SB,0x20000),(DL,0x10000),(0x60000000,0x20000),(0x10000000,4096)]:u.mem_map(a,n)
    u.mem_write(SB+0x8d00,(O/'prepare-v3-after.bin').read_bytes());u.mem_write(SB+0x9630,(O/'bootstrap-v3-after.bin').read_bytes())
    calls=[]
    def hook(u,a,n,data):
        if a not in [DL+0xbb0,DL+0xc48,0x10000000]:return
        assert u.reg_read(UC_ARM_REG_SP)%8==0
        if a==DL+0xbb0:
            text=bytes(u.mem_read(u.reg_read(UC_ARM_REG_R0),100)).split(b'\0')[0]
            assert text==b'/log/yc_observer/yc_probe_v3.so',text
            assert u.reg_read(UC_ARM_REG_R1)==0x102
            v=0 if fail=='dlopen' else 123;calls.append('dlopen')
        elif a==DL+0xc48:
            text=bytes(u.mem_read(u.reg_read(UC_ARM_REG_R1),100)).split(b'\0')[0]
            assert text==b'yc_observer_activate',text
            v=0 if fail=='dlsym' else 0x10000001;calls.append('dlsym')
        else:v=0 if fail=='activation' else 1;calls.append('activate')
        for r in regs[:4]:u.reg_write(r,0xdeadbeef)
        u.reg_write(UC_ARM_REG_R0,v);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
    u.hook_add(UC_HOOK_CODE,hook)
    values=[0x71000000+i for i in range(12)]
    for r,v in zip(regs,values):u.reg_write(r,v)
    u.reg_write(UC_ARM_REG_SP,0x60010000);u.reg_write(UC_ARM_REG_LR,0x12345679)
    u.emu_start((SB+0x8d00)|1,SB+0x90c0,count=1000)
    assert u.reg_read(UC_ARM_REG_PC)==SB+0x90c0
    assert u.reg_read(UC_ARM_REG_SP)==0x60010000 and u.reg_read(UC_ARM_REG_LR)==0x12345679
    assert [u.reg_read(r) for r in regs]==values
    results.append({'case':fail,'calls':calls,'always_continues_original_persistent_gate':True})
(O/'bootstrap-v3-verification.json').write_text(json.dumps(results,indent=2)+'\n')
print('Bootstrap checks passed:',len(results))
