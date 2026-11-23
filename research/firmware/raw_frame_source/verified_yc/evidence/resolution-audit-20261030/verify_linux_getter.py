from pathlib import Path
import importlib.util,struct,json
from unicorn import *
from unicorn.arm_const import *
ROOT=Path(r'D:/02_Development_And_Projects/pmca-re');OUT=Path('.local/outputs/yc-resolution-audit-20261030')
spec=importlib.util.spec_from_file_location('support',ROOT/'research/firmware/yuy2_transport_v25/verify_support.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
u=Uc(UC_ARCH_ARM,UC_MODE_ARM);handlers={};calls=[]
for a,n in [(0x10000000,0x10000),(0x40000000,0x10000),(m.STOP,4096),(0x60000000,0x20000)]:u.mem_map(a,n)
def imp(name):
 a=0x10000000+len(handlers)*4;handlers[a]=name;return a
sdk=m.load(u,ROOT/'.local/dumps/camera_2025/usr/usr/lib/dataflowInfraFramework.so',0x08000000,imp)
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

obj=0x40000000;raw=0x40001000;entry=0x40004000;output=0x40005000
rows=[]
real=Path('.local/outputs/vga-v39/capture-first-01/logs/rejected-source.yc38').read_bytes()[80:4176]
ref=Path('.local/outputs/vga-v33/capture-first-01/logs/source-ssyc-retained.bin').read_bytes()
bad=Path('.local/outputs/vga-v38/capture-first-01/logs/rejected-source.yc38').read_bytes()[80:4176]
getall=next(n for n in sdk if 'ImageSizeInfo11GetData_All' in n and 'Right' not in n)
for name,data,expected in [('actual_v39_no_image',real,0),('reference_attached_image',ref,0),('actual_v38_malformed',bad,0xfffffff2)]:
 u.mem_write(raw,data);u.mem_write(output,bytes(60))
 run('_ZN26C_DataflowInfra_StdData_YCC1Ejjj',obj,raw,len(data),0)
 run('_ZN35C_DataflowInfra_Entry_ImageSizeInfoC1Ev',entry)
 rc=run('_ZN26C_DataflowInfra_StdData_YC22GetEntry_ImageSizeInfoEP35C_DataflowInfra_Entry_ImageSizeInfo',obj,entry)
 assert rc==expected,(name,hex(rc))
 if not rc:run(getall,entry,output)
 wire=bytes(u.mem_read(output,60));rows.append(dict(case=name,returncode=rc,image_hex=wire.hex()))
 if not rc:assert wire==data[64:124]
result=dict(camera_access=False,original_Linux_SDK_code_executed=True,metadata_API='C_DataflowInfra_StdData_YC::GetEntry_ImageSizeInfo then Entry_ImageSizeInfo::GetData_All',cases=rows,hardware_mapping_mocked=True,conclusion='Original exported Linux accessors resolve category0 directly from a supplied SDS mapping; no raw-memory signature search is required.')
(OUT/'linux-native-getter.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

