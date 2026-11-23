"""Execute the original Linux movie-format depth-name mapper; not a live producer proof."""
from pathlib import Path
import importlib.util,json
from unicorn import *
from unicorn.arm_const import *
spec=importlib.util.spec_from_file_location('support','.local/work/vga-v40/recipe/verify_support.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(m.STOP,4096);u.mem_map(0x60000000,0x20000)
base=0x08000000
m.load(u,Path('D:/02_Development_And_Projects/pmca-re/.local/dumps/camera_2025/usr/usr/lib/libObj.so'),base,lambda name:0x10000000)
rows=[]
for value,expected in [(0,'VIDEO_BIT_DEPTH_8BIT'),(1,'VIDEO_BIT_DEPTH_10BIT'),(255,'VIDEO_BIT_DEPTH_INVALID')]:
 u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,m.STACK);u.reg_write(UC_ARM_REG_LR,m.STOP);u.reg_write(UC_ARM_REG_R0,0);u.reg_write(UC_ARM_REG_R1,value)
 u.emu_start(base+0x95d5cc+1,m.STOP,count=1000)
 assert u.reg_read(UC_ARM_REG_PC)==m.STOP
 label=m.cstr(u,u.reg_read(UC_ARM_REG_R0));assert label==expected,(value,label)
 rows.append({'recording_format_enum':value,'label':label})
out={'original_function':'libObj.so+0x95d5cc','original_code_executed':True,'camera_access':False,'cases':rows,'limitation':'Recording-format enum names do not prove an active YC producer, pixel precision or identity with SSYC byte0x36.'}
Path('.local/outputs/yc-high-depth-20261030/movie-depth-names-verification.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
