"""Execute dfe_dat ARM command decoder with RAM operands only.

The image contains code, not just calibration tables. This test does not
establish how its local address space maps to the camera's main CPU or sensor.
"""
import argparse,hashlib,json,struct
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM
from unicorn.arm_const import *
from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM
p=argparse.ArgumentParser(description=__doc__);p.add_argument('repo',type=Path);a=p.parse_args()
data=(a.repo/'dumps/firmware/dfe_dat.bin').read_bytes()
assert hashlib.md5(data).hexdigest()=='8c5f3b191dd124cf1ee2cb5055cec37e'
base=0x01000000;mem=0x40000000;stack=0x50001000;stop=0x60000000
u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
for addr,size in [(base,0x10000),(mem,0x4000),(stack-0x1000,0x2000),(stop,0x1000)]:u.mem_map(addr,size)
u.mem_write(base,data)
def put(addr,value):u.mem_write(addr,struct.pack('<I',value))
def word(addr):return struct.unpack('<I',u.mem_read(addr,4))[0]
rows=[]
for index in [0,1,61]:
    for command in [0,1,2,5,0xffffffff]:
        for count in [index,index+1]:
            u.mem_write(mem,bytes(0x4000))
            put(mem+0x2000,count)
            put(mem+0x10+index*12,command)
            put(mem+0x14+index*12,mem+0x3000)
            put(mem+0x18+index*12,0x12345678)
            put(mem+0x3000,0x89abcdef)
            u.reg_write(UC_ARM_REG_CPSR,0x10)
            u.reg_write(UC_ARM_REG_SP,stack)
            u.reg_write(UC_ARM_REG_LR,stop)
            for reg,value in [(UC_ARM_REG_R0,mem),(UC_ARM_REG_R1,index),(UC_ARM_REG_R2,mem+0x2000)]:u.reg_write(reg,value)
            u.emu_start(base+0x1d4,stop,count=1000)
            assert u.reg_read(UC_ARM_REG_PC)==stop
            assert u.reg_read(UC_ARM_REG_SP)==stack
            status=u.mem_read(mem+1,1)[0]
            assert status==(2 if count<=index else int(command not in [0,1,2]))
            expected_target=0x12345678 if command==1 and count>index else 0x89abcdef
            expected_result=0x89abcdef if command==2 and count>index else 0x12345678
            assert word(mem+0x3000)==expected_target
            assert word(mem+0x18+index*12)==expected_result
            rows.append(dict(index=index,count=count,command=command,status=status,
                             target=hex(word(mem+0x3000)),command_result=hex(word(mem+0x18+index*12))))
c=Cs(CS_ARCH_ARM,CS_MODE_ARM);c.skipdata=True
disasm='\n'.join(f'{i.address:08x}: {i.mnemonic} {i.op_str}' for i in c.disasm(data,base))
(Path(__file__).parent/'dfe-core-arm-disassembly.txt').write_text(disasm)
print(json.dumps(dict(cases=len(rows),image_md5=hashlib.md5(data).hexdigest(),size=len(data),
    image_base_inferred_from_vectors=hex(base),reset_vector=hex(struct.unpack_from('<I',data,0x20)[0]),
    build_string=data[0xffe0:].split(b'\0')[0].decode('ascii'),native_executor=hex(base+0x1d4),
    command_record_offset='context + 0x10 + index*12',mocks=[],operands='RAM fixtures',
    sensor_dma_or_cadence_emulated=False,rows=rows),indent=2))
