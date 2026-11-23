"""Validate config-byte forwarding and the actual ELF virtual dispatch offline."""
import sys,json,struct,importlib.util
from pathlib import Path
from unicorn import *
from unicorn.arm_const import *
sys.path.insert(0,'.local/work/yc-frame-contract-20261029')
from rtos_harness import Harness,MEM,STACK
h=Harness();rows=[]
for value in [0,1,2,10,12,255]:
 h.put(0x64277f68+0x34,MEM);h.u.mem_write(MEM+0x37,bytes([value]));h.u.mem_write(0x6414fb40+0x36,b'\xa5')
 assert h.run(0x637cd6b0)==value
 h.u.reg_write(UC_ARM_REG_CPSR,0x10);h.u.reg_write(UC_ARM_REG_SP,STACK)
 h.u.emu_start(0x637cf926|1,0x637cf92e,count=100)
 assert h.u.reg_read(UC_ARM_REG_PC)==0x637cf92e
 got=h.u.mem_read(0x6414fb40+0x36,1)[0];assert got==int(value!=0)
 rows.append({'config_37':value,'getter':value,'downstream_36':got})
assert h.run(0x638513e4)==0x6414fb40
spec=importlib.util.spec_from_file_location('support','.local/work/vga-v40/recipe/verify_support.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
u=Uc(UC_ARCH_ARM,UC_MODE_ARM);base=0x08000000
m.load(u,Path('D:/02_Development_And_Projects/pmca-re/.local/dumps/camera_2025/usr/usr/lib/libmpr.so'),base,lambda n:0x10000000)
u.mem_map(0x40000000,0x40000);u.mem_map(0x60000000,0x20000)
def invalid(u,access,address,size,value,_):
 print('invalid',hex(address),'pc',hex(u.reg_read(UC_ARM_REG_PC)),'sp',hex(u.reg_read(UC_ARM_REG_SP)));return False
u.hook_add(UC_HOOK_MEM_INVALID,invalid)
obj=0x40000000;source=obj+0x10000;dest=obj+0x20000;frame=0x60008000
assert m.word(u,base+0xa0c798)==base+0x3f6371
assert m.word(u,base+0xa0c79c)==base+0x3f6283
virtual=[]
for color in [0,1]:
 for depth in [0,1,2]:
  u.mem_write(dest,bytes(256));m.put(u,obj,base+0xa0c788);m.put(u,source+8,8);m.put(u,source+0x68,color);m.put(u,source+0x6c,depth)
  m.put(u,frame+0x24,0x100)
  u.reg_write(UC_ARM_REG_CPSR,0x10)
  for reg,value in [(UC_ARM_REG_R8,obj),(UC_ARM_REG_R5,source),(UC_ARM_REG_R4,dest),(UC_ARM_REG_R7,frame),(UC_ARM_REG_SP,frame-0x100),(UC_ARM_REG_R9,0),(UC_ARM_REG_R0,0)]:u.reg_write(reg,value)
  u.reg_write(UC_ARM_REG_CPSR,0x10);u.emu_start(base+0x3f639c+1,base+0x3f63c0,count=1000)
  assert u.reg_read(UC_ARM_REG_PC)==base+0x3f63c0
  expected=(0x43+color) if depth==1 else 0x18;assert m.word(u,dest+0xc)==expected
  virtual.append({'color':color,'depth':depth,'public_quality':expected,'error_flag':u.mem_read(dest,1)[0]})
result={'offline_only':True,'original_instructions':True,'config_getter':'0x637cd6b0','forwarding_pair':['0x637cf926','0x637cf92a'],'setter':'0x638514c0','downstream_structure':'0x6414fb40','config_cases':rows,'vtable_address_point':'libmpr.so+0xa0c788','vtable_depth_converter_slot':'0x14','virtual_dispatch_cases':virtual,'limits':['Configuration forwarding is not proof of physical pixel precision.','No allocation, sensor, ISP or hardware IPC was emulated.','Virtual dispatch executed a bounded original converter slice with a saved ELF vtable and controlled object; it does not prove live object selection.']}
Path('.local/outputs/yc-native-setup-20261030/verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
