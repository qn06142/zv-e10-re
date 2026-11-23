"""Check original Sony Thumb colour/mute accessors against our single-word update.
No camera interaction. Requires the privately held unmodified av-cam.bin.
"""
from pathlib import Path
import hashlib,json,struct,sys
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_LR,UC_ARM_REG_SP,UC_ARM_REG_PC


def verify(image):
    # Local reference differs in other parts of the image. Relevant code pages
    # were read from the current camera (MD5 90096db2...) and matched exactly.
    assert hashlib.md5(image).hexdigest()=='cdcae9d4fdbf66a33704a4c7564e346d'
    expected={0x493000:'62b5c7591ab8bf9482b05a58eeab947af86c5d5c934dbd1cb5c56408d1100bf7',
              0x4b4000:'efed43126d55171348c0911cf6b37ebb99ef3a6c23463d7ead523434027dfbdd',
              0x807000:'1781d2078baecfcf21bcbfcba9ac4842a7e795feb8114e6e98509b5e4023e028'}
    for offset,digest in expected.items():
        assert hashlib.sha256(image[offset:offset+4096]).hexdigest()==digest
    base=0x635c6000;register=0xf3445108;results=[]
    for initial in (0x00000000,0x84012345,0xffffffff):
        for y in (16,235):
            cpu=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
            cpu.mem_map(base,(len(image)+4095)&~4095);cpu.mem_write(base,image)
            cpu.mem_map(0xf3445000,4096);cpu.mem_write(register,struct.pack('<I',initial))
            cpu.mem_map(0x2000000,8192);cpu.mem_map(0x2100000,4096)
            cpu.reg_write(UC_ARM_REG_SP,0x2002000);writes=[]
            def write(cpu,access,address,size,value,_):
                if 0xf0000000<=address:
                    assert address==register and size==4;writes.append(value)
                else:assert 0x2000000<=address<0x2002000
            cpu.hook_add(UC_HOOK_MEM_WRITE,write)
            def call(offset,a,b=0,c=0):
                cpu.reg_write(UC_ARM_REG_R0,a);cpu.reg_write(UC_ARM_REG_R1,b);cpu.reg_write(UC_ARM_REG_R2,c)
                cpu.reg_write(UC_ARM_REG_LR,0x2100001)
                cpu.emu_start((base+offset)|1,0x2100000,count=500)
                assert cpu.reg_read(UC_ARM_REG_PC)==0x2100000
                assert cpu.reg_read(UC_ARM_REG_SP)==0x2002000
            # Native combined colour setter, plus native upper two control setters.
            call(0x807c1c,y,128,128);call(0x807c14,1);call(0x807c18,1)
            final=struct.unpack('<I',cpu.mem_read(register,4))[0]
            expected=(initial&0xff000000)|0x03000000|(y<<16)|0x8080
            assert final==expected,(hex(final),hex(expected))
            assert len(writes)==5
            results.append({'initial':hex(initial),'y':y,'native_final':hex(final),'matches_runtime_update':True})
    return {'status':'original-native-colour-control-instructions-verified','cases':results,
            'hardware_effect':'not established by this offline check','controller_word':'0xf3445108'}


if __name__=='__main__':print(json.dumps(verify(Path(sys.argv[1]).read_bytes())))
