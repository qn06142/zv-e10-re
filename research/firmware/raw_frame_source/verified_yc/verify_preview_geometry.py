from pathlib import Path
Path("outputs/yc-live-20261026").mkdir(parents=True,exist_ok=True)
import struct,json
from unicorn import *
from unicorn.arm_const import *
B=Path(r'D:/02_Development_And_Projects/pmca-re/dumps/firmware/av-cam.bin').read_bytes();BASE=0x635c6000
u=Uc(UC_ARCH_ARM,UC_MODE_THUMB);u.mem_map(BASE,(len(B)+4095)&~4095);u.mem_write(BASE,B)
for a,n in [(0x40000000,0x20000),(0x50000000,4096),(0x60000000,0x20000)]:u.mem_map(a,n)
rows=[]
for i in range(9):
 raw=B[0x63e43e9c-BASE+20*i:0x63e43e9c-BASE+20*(i+1)];dim=struct.unpack_from('<4H',raw);types=struct.unpack_from('<2I',raw,8);compress=struct.unpack_from('<I',raw,16)[0]
 rows.append(dict(index=i,dimensions=dim,unit_type_if_content2=hex(types[0]),unit_type_other_content=hex(types[1]),yc_compress=compress,raw=raw.hex()))
cases=[]
for w,h in [(640,480),(1920,1080),(1280,720),(1440,1080),(720,240),(720,288),(123,456)]:
 u.mem_write(0x40000000,b'\xa5'*32);u.reg_write(UC_ARM_REG_R0,0x40000000);u.reg_write(UC_ARM_REG_R1,w);u.reg_write(UC_ARM_REG_R2,h);u.reg_write(UC_ARM_REG_SP,0x60010000);u.reg_write(UC_ARM_REG_LR,0x50000001)
 u.emu_start(0x6372e57d,0x50000000,count=5000);assert u.reg_read(UC_ARM_REG_PC)==0x50000000
 out=bytes(u.mem_read(0x40000000,32));assert out[20:]==b'\xa5'*12
 selected=[r['index'] for r in rows if r['raw']==out[:20].hex()];assert selected
 cases.append(dict(width=w,height=h,selected_rows=selected,output=out[:20].hex()))
 assert (w!=640 or selected==[1])
 print(w,h,selected)
report=dict(actual_Sony_function_executed='0x6372e57c',external_calls_stubbed=False,camera_access=False,table='0x63e43e9c',record_bytes=20,record_count=9,rows=rows,cases=cases)
Path('outputs/yc-live-20261026/preview-geometry-execution.json').write_text(json.dumps(report,indent=2))
