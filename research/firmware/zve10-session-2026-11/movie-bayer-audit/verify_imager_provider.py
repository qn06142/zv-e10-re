"""Recover IMX284 mode records through original native construction and initialization.
Run from workspace: python verify_imager_provider.py REPOSITORY
No sensor transfers or live frame cadence are simulated.
"""
import sys,json,argparse,struct
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('repo',type=Path);a=p.parse_args()
sys.path.insert(0,str(a.repo/'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness,MEM
from unicorn.arm_const import UC_ARM_REG_C1_C0_2,UC_ARM_REG_FPEXC,UC_ARM_REG_R0,UC_ARM_REG_R1
h=Harness();h.u.reg_write(UC_ARM_REG_C1_C0_2,0xf00000);h.u.reg_write(UC_ARM_REG_FPEXC,0x40000000)
for fn in [0x63ae1ba4,0x6396f8c4]:h.callbacks[fn]=lambda _:h.ret(0)
# Original concrete driver constructor also creates its geometry input and provider.
h.run(0x637abbe4,MEM,0)
provider=h.word(MEM+0x284)
assert provider==MEM+0x3c4 and h.word(provider)==0x64588fb0
assert h.word(provider+4)==23
# Native caller 0x637ae374 passes the constructed InitParam at driver+0x134.
# driver+0x28c is a different record and is not a valid substitute.
h.run(0x63d2b564,provider,0,MEM+0x134)
clock_record=h.word(provider+0x24)
clock_value=struct.unpack("<H",h.u.mem_read(clock_record+2,2))[0]
assert clock_value==72
assert struct.unpack("<H",h.u.mem_read(MEM+0x168,2))[0]==clock_value
packets={int(x['sensor_mode'],16):x for x in json.loads((Path(__file__).parent/'sensor-mode-results.json').read_text())['rows']}
rows=[]
for n in range(23):
 sensor=h.word(h.word(provider+8)+4*n)
 head=h.run(0x637ad4c8,provider,n,0);tim=h.run(0x637ad4f0,provider,n,0)
 mapping=packets[sensor];assert int(mapping['resource'],16)
 native_h=h.word(provider+0x38)+n*24
 h.run(0x63d2b4ba,native_h,clock_record)
 h_period=struct.unpack('<d',struct.pack('<II',h.u.reg_read(UC_ARM_REG_R0),h.u.reg_read(UC_ARM_REG_R1)))[0]
 vd_num=struct.unpack('<H',h.u.mem_read(head+0x18,2))[0]
 frame_period=h_period*h.word(tim+12)*vd_num
 geom=h.run(0x637ad518,provider,n,0)
 rows.append(dict(index=n,sensor_mode=hex(sensor),drive_mode=mapping['drive_mode'],native_packet_bits=mapping['native_bit_length'],header_hex=bytes(h.u.mem_read(head,0x30)).hex(),timing_hex=bytes(h.u.mem_read(tim,0x78)).hex(),H=h.word(tim+8),V=h.word(tim+12),H_fraction_bytes=bytes(h.u.mem_read(tim+0x10,3)).hex(),vd_num=vd_num,native_h_period=h_period,derived_frame_period=frame_period,inferred_fps=1e6/frame_period,geometry_hex=bytes(h.u.mem_read(geom,0x38)).hex()))
assert all(r['H'] and r['V'] for r in rows)
by_sensor={int(r['sensor_mode'],16):r for r in rows}
for sensor in [0x1f,0xb5]:
 assert by_sensor[sensor]['vd_num']==2
 assert abs(by_sensor[sensor]['inferred_fps']-24000/1001)<1e-9
assert abs(by_sensor[0x89]['inferred_fps']-25)<1e-9
result=dict(cases=len(rows),mocks=['atexit registration','logger'],harness_memory_helpers=['memcpy','memset'],constructor='0x637abbe4',provider_constructor='0x637ad5fc',provider_vtable=hex(h.word(provider)),native_init_parameter_offset='0x134',native_clock_value=clock_value,native_h_period_function='0x63d2b4ba',fps_units_inferred=True,cadence_measured=False,rows=rows)
print(json.dumps(result,indent=2))
