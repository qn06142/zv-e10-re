"""Recover field offsets by running Sony's real metadata printer and real getter."""
from pathlib import Path
import importlib.util,json,hashlib,re
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
ROOT=Path(r'D:/02_Development_And_Projects/pmca-re');OUT=Path('outputs/yc-source-re-20261025')
spec=importlib.util.spec_from_file_location('support',ROOT/'research/firmware/yuy2_transport_v25/verify_support.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
u=Uc(UC_ARCH_ARM,UC_MODE_ARM);handlers={};printed=[]
for a,n in [(0x10000000,0x20000),(0x40000000,0x10000),(m.STOP,4096),(0x60000000,0x20000)]:u.mem_map(a,n)
def imp(name):
 if 'ImageSizeInfo11GetData_All' in name and 'Right' not in name:return 0x08000000+0x246d7
 at=0x10000000+len(handlers)*4;handlers[at]=name;return at
m.load(u,ROOT/'dumps/camera_2025/usr/usr/lib/dataflowInfraFramework.so',0x08000000,imp)
m.load(u,ROOT/'dumps/camera_2025/usr/usr/lib/libObj.so',0x20000000,imp)
entry=0x40000000;pattern=bytes(range(60));u.mem_write(entry+20,pattern)
def hook(u,a,n,d):
 if a not in handlers:return
 name=handlers[a];r=[u.reg_read(x) for x in m.R]
 if name=='printf':printed.append({'format':m.cstr(u,r[0]),'value':r[1],'call_return':hex(u.reg_read(UC_ARM_REG_LR)-0x20000000)});value=0
 elif name in ['memcpy','memmove']:u.mem_write(r[0],bytes(u.mem_read(r[1],r[2])));value=r[0]
 else:raise AssertionError((name,hex(a)))
 u.reg_write(UC_ARM_REG_R0,value);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
u.hook_add(UC_HOOK_CODE,hook);u.reg_write(UC_ARM_REG_R0,0x40001000);u.reg_write(UC_ARM_REG_R1,entry);u.reg_write(UC_ARM_REG_SP,m.STACK);u.reg_write(UC_ARM_REG_LR,m.STOP)
u.emu_start(0x202c3679,m.STOP,count=10000);assert u.reg_read(UC_ARM_REG_PC)==m.STOP
layout=[]
for row in printed:
 value=row['value'];matches=[]
 for width in [1,2,4]:
  for offset in range(61-width):
   if int.from_bytes(pattern[offset:offset+width],'little')==value:matches.append((offset,width))
 assert len(matches)==1,(row,matches)
 offset,width=matches[0];label=re.findall(r'(\w+)\s*\[',row['format'])[-1]
 row.update(field=label,offset=offset,width=width);layout.append(row);print(f'{offset:02x} {width} {label}')
assert len(layout)>=20,len(layout)
result={'method':'Executed libObj.so printer0x2c3678 with real framework getter0x246d6 on byte-tagged60-byte fixture; printf intercepted only','camera_access':False,'format_enums_proven':False,'fields':layout}
(OUT/'image-size-layout-verified.json').write_text(json.dumps(result,indent=2))
