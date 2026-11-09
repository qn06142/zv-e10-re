"""Compare original Thumb parameter publisher and ARM parameter derivation.

The same captured bytes cross the two emulators explicitly. This is a software
ABI check, not an emulated physical shared-memory bus or recovered pixel frame.
"""
import argparse,json,struct,sys
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM
from unicorn.arm_const import *
p=argparse.ArgumentParser(description=__doc__);p.add_argument('repo',type=Path);a=p.parse_args()
sys.path.insert(0,str(a.repo/'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness,MEM
from rtos import word as firmware_word
h=Harness();rom=h.run(0x639dfcac)
defaults=[h.word(rom+i) for i in range(0,48,4)]
u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x01000000,0x40000)
u.mem_map(0x01098000,0x1000)
u.mem_write(0x01000000,(a.repo/'dumps/firmware/dfe_dat.bin').read_bytes())
u.mem_map(0x50000000,0x2000);u.mem_map(0x60000000,0x1000)
def word(addr):return struct.unpack('<I',u.mem_read(addr,4))[0]
rows=[];port_rows=[]
for mode in [0,0x10]:
    for crop0,crop1 in [(0,0),(0,12),(1,3),(4,8),(7,16),(1521,0)]:
        values=list(defaults);values[10:12]=[crop0,crop1]
        wrapper,record,destination=MEM,MEM+0x100,MEM+0x1000
        h.put(wrapper,destination)
        h.u.mem_write(record,struct.pack('<12I',*values))
        h.u.mem_write(destination,bytes([0xa5])*0x100)
        h.run(0x63da0ab6,wrapper,mode,record)
        blob=bytes(h.u.mem_read(destination,0x100))
        assert struct.unpack_from('<12I',blob,0x20)==tuple(values)
        assert struct.unpack_from('<I',blob,0xfc)[0]==mode
        u.mem_write(0x01030000,blob)
        u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,0x50001000)
        u.reg_write(UC_ARM_REG_LR,0x60000000)
        u.reg_write(UC_ARM_REG_R0,0x01030000);u.reg_write(UC_ARM_REG_R1,mode)
        u.emu_start(0x01001870,0x60000000,count=1000)
        assert u.reg_read(UC_ARM_REG_PC)==0x60000000
        assert u.reg_read(UC_ARM_REG_SP)==0x50001000
        v=values;aligned0=crop0&~3;aligned1=crop1&~3
        width=(v[0]-aligned0-aligned1)&0xffffffff
        base=(v[4]+aligned0)&0xffffffff
        selected=v[8:10] if mode&0x10 else v[6:8]
        expected={0x50:width,0x54:v[1],0x58:v[2],0x5c:v[3],
                  0x60:base,0x64:v[5],0x68:selected[0],0x6c:selected[1],
                  0x70:v[2],0x74:v[3],0x78:base,0x7c:v[5],
                  0x80:selected[0],0x84:selected[1],0x88:crop0&3,0x8c:0,
                  0x90:(width-(crop0&3)-(crop1&3))&0xffffffff,
                  0x94:v[1],0x98:v[2],0x9c:v[3],0xa0:base,0xa4:v[5],
                  0xa8:selected[0],0xac:selected[1],
                  0xb0:(width-(crop0&3)-(crop1&3))&0xffffffff,
                  0xb4:v[1],0xb8:crop0&3}
        for offset,value in expected.items():
            assert word(0x01030000+offset)==value,(mode,crop0,crop1,hex(offset))
        rows.append(dict(mode=mode,crop0=crop0,crop1=crop1,
            derived_width=width,derived_final_width=expected[0x90],
            selected_pair=[hex(n) for n in selected]))
        # Original register configurator consumes this derived block. The +4
        # subconfiguration field and plane selector are explicit RAM fixtures.
        for plane in [0,1]:
            u.mem_write(0x01030004,bytes(4))
            u.mem_write(0x01098000,bytes(0x1000))
            u.mem_write(0x50001000,struct.pack('<I',plane))
            u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,0x50001000)
            u.reg_write(UC_ARM_REG_LR,0x60000000)
            for reg,value in [(UC_ARM_REG_R0,0x01030100),(UC_ARM_REG_R1,0x01030000),
                              (UC_ARM_REG_R2,mode),(UC_ARM_REG_R3,0)]:u.reg_write(reg,value)
            u.emu_start(0x01001e3c,0x60000000,count=1000)
            assert u.reg_read(UC_ARM_REG_PC)==0x60000000
            assert u.reg_read(UC_ARM_REG_SP)==0x50001000
            observed=[]
            for port in [2,3]:
                regbase=0x01098000+0x200+port*0x80
                values4=[word(regbase+offset) for offset in [0x20,0x24,0x28,0x2c]]
                assert values4==[selected[plane]|0xfe000000,(width*2)&0xffffffff,
                                 ((v[2]-width)*2)&0xffffffff,v[1]-1]
                assert all(word(regbase+offset)==0 for offset in range(0x30,0x48,4))
                observed.append(dict(port=port,register_base=hex(regbase),
                                     address=hex(values4[0]),line_bytes=values4[1],
                                     gap_bytes=values4[2],lines_minus_one=values4[3]))
            port_rows.append(dict(mode=mode,crop0=crop0,crop1=crop1,plane=plane,ports=observed))
# Cross-check the register banks against the native host AIF constructor and
# test their enable bits in the native default mode resources.
host_ports=[]
for port in [2,3]:
    h.run(0x637a3be0,MEM+0x2000,1,port)
    assert h.word(MEM+0x2004)==0xfc098000
    assert bytes(h.u.mem_read(MEM+0x2008,1))[0]==port
    host_ports.append(dict(kind=1,port=port,base='0xfc098000',
                           register_base=hex(0xfc098000+0x200+port*0x80)))
h.run(0x6379bf60)
table=firmware_word(0x64638120+0x4490)
resources={h.word(h.word(table+i*4)+4):h.word(table+i*4) for i in range(27)}
mode_rows=[]
for mode in range(0x95):
    resource=h.run(0x637a6d78,mode,MEM+0x3000)
    if not resource:continue
    obj=resources[resource]
    enabled=[h.run(0x63d22c70,obj,index) for index in [0,1]]
    assert enabled==[0,0]
    mode_rows.append(dict(drive_mode=hex(mode),resource=hex(resource),
                          flags=hex(h.word(obj+0x28)),aif_enable_bits=enabled))
assert len(mode_rows)==23
print(json.dumps(dict(cases=len(rows),native_host_publisher='0x63da0ab6',
    native_arm_consumer='0x01001870',rom_parameter_getter='0x639dfcac',
    rom_parameters_address=hex(rom),rom_words=[hex(v) for v in defaults],
    native_arm_register_configurator='0x01001e3c',register_config_cases=len(port_rows),
    mocks=[],explicit_fixtures=['RAM wrapper and destination','mode bits','crop arguments',
                               'zero subconfiguration +4','plane selector','RAM-backed formatter registers'],
    cross_cpu_bytes_copied_by_test=True,physical_bus_emulated=False,pixels_emulated=False,
    rows=rows,register_rows=port_rows,host_port_crosscheck=host_ports,
    native_default_mode_resource_cases=len(mode_rows),default_mode_rows=mode_rows),indent=2))
