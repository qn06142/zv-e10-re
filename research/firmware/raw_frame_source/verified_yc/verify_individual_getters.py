from pathlib import Path
import importlib.util,struct,json
from unicorn import *
from unicorn.arm_const import *
ROOT = Path(r'D:/02_Development_And_Projects/pmca-re')
OUT = Path(r'C:/Users/qn061/Documents/Codex/2026-10-22/chec/outputs/yc-source-re-20261025') if not Path('outputs/yc-source-re-20261025').is_dir() else Path('outputs/yc-source-re-20261025')
spec=importlib.util.spec_from_file_location('support',ROOT/'research/firmware/yuy2_transport_v25/verify_support.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
u=Uc(UC_ARCH_ARM,UC_MODE_ARM);handlers={};calls=[]
for a,n in [(0x10000000,0x10000),(0x40000000,0x10000),(m.STOP,4096),(0x60000000,0x20000)]:u.mem_map(a,n)
def imp(name):
 a=0x10000000+len(handlers)*4;handlers[a]=name;return a
sdk=m.load(u,ROOT/'dumps/camera_2025/usr/usr/lib/dataflowInfraFramework.so',0x08000000,imp)
def hook(u,a,n,d):
 if a not in handlers:return
 name=handlers[a];r=[u.reg_read(x) for x in m.R];calls.append(name)
 if name in sdk:u.reg_write(UC_ARM_REG_PC,sdk[name]);return
 if name=='memset':u.mem_write(r[0],bytes([r[1]&255])*r[2]);v=r[0]
 elif name=='memcpy':u.mem_write(r[0],bytes(u.mem_read(r[1],r[2])));v=r[0]
 elif name in ['memcmp','strncmp']:v=int(bytes(u.mem_read(r[0],r[2]))!=bytes(u.mem_read(r[1],r[2])))
 else:raise AssertionError((name,[hex(x) for x in r]))
 u.reg_write(UC_ARM_REG_R0,v);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
u.hook_add(UC_HOOK_CODE,hook)
def run(name,*args):
 u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,m.STACK);u.reg_write(UC_ARM_REG_LR,m.STOP)
 for r,v in zip(m.R,args):u.reg_write(r,v)
 u.emu_start(sdk[name],m.STOP,count=50000);assert u.reg_read(UC_ARM_REG_PC)==m.STOP;return u.reg_read(UC_ARM_REG_R0)


entry=0x40000000;output=0x40001000;pattern=bytes(range(60));u.mem_write(entry+20,pattern)
fields=[]
import re
for name in sdk:
 if 'C_DataflowInfra_Entry_ImageSizeInfo' not in name or 'GetData_' not in name or 'GetData_All' in name:continue
 u.mem_write(output,b'\xa5'*32);run(name,entry,output)
 raw=bytes(u.mem_read(output,32));width=next((i for i,v in enumerate(raw) if v==0xa5),32)
 if width not in [1,2,4]:print('skip structure',name,width);continue
 assert raw[width:]==b'\xa5'*(32-width)
 offsets=[i for i in range(61-width) if pattern[i:i+width]==raw[:width]];assert len(offsets)==1
 field=re.search(r'GetData_(\w+)E',name).group(1)
 row=dict(field=field,offset=offsets[0],width=width,value=int.from_bytes(raw[:width],'little'),symbol=name,address=hex(sdk[name]-0x08000000));fields.append(row);print(field,hex(offsets[0]),width)
(OUT/'image-size-individual-getters.json').write_text(json.dumps({'actual_Sony_getters_executed':True,'camera_access':False,'numeric_enum_meanings_proved':False,'fields':fields},indent=2))
