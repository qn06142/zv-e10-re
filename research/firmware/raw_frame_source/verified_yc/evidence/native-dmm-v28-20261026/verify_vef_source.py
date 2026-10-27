from pathlib import Path
import struct,json
from unicorn import *
from unicorn.arm_const import *
B=Path(r'D:/02_Development_And_Projects/pmca-re/dumps/firmware/av-cam.bin').read_bytes();BASE=0x635c6000
u=Uc(UC_ARCH_ARM,UC_MODE_THUMB);u.mem_map(0x63000000,0x2000000);u.mem_write(BASE,B);u.mem_map(0x50000000,0x1000);u.mem_map(0x60000000,0x20000);STACK=0x60010000;STOP=0x50000000
calls=[]
def hook(u,a,n,d):
 if a==0x63c5fe48:calls.append(a);u.reg_write(UC_ARM_REG_R0,0);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
u.hook_add(UC_HOOK_CODE,hook)
def run(addr,*args):
 u.reg_write(UC_ARM_REG_CPSR,0x30);u.reg_write(UC_ARM_REG_SP,STACK);u.reg_write(UC_ARM_REG_LR,STOP|1)
 for r,v in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],args):u.reg_write(r,v)
 for i,v in enumerate(args[4:]):u.mem_write(STACK+i*4,struct.pack('<I',v))
 u.emu_start(addr|1,STOP,count=200000);assert u.reg_read(UC_ARM_REG_PC)==STOP;return u.reg_read(UC_ARM_REG_R0)
rows=[]
for mode in range(2,12):
 run(0x63761e68,mode,1,1)
 table=struct.unpack('<I',u.mem_read(0x6425961c,4))[0];count=struct.unpack('<H',u.mem_read(0x6449a782,2))[0]
 if table!=0x645b580c:continue
 for w,h in [(1920,1080),(1280,720),(640,480)]:
  record=run(0x63761dcc,2,0,w,h,0x41,0x41)
  assert record and table<=record<table+count*56,(mode,w,h,hex(record))
  unit=struct.unpack('<I',u.mem_read(record+40,4))[0];assert unit==0x295,(mode,w,h,hex(unit))
  rows.append({'mode':mode,'geometry':[w,h],'table':hex(table),'native_record':hex(record),'record_stride':56,'unit_offset':40,'unit_type':hex(unit)})
assert len(rows)>=3
report={'native_RTOS_setter_and_geometry_lookup_executed':True,'print_service_only_mocked':True,'camera_access':False,'cases':rows}
Path('outputs/native-dmm-v28/vef-type295-native-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
