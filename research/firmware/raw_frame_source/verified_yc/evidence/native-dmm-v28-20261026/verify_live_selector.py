from pathlib import Path
import importlib.util,json,struct
from unicorn import *
from unicorn.arm_const import *
O=Path('outputs/native-dmm-callback/deployment/live/first-capture-01');W=Path('work/native-dmm-callback/recipe');spec=importlib.util.spec_from_file_location('support',W/'verify_support.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
u=Uc(UC_ARCH_ARM,UC_MODE_ARM);handlers={}
for a,n in [(0x10000000,0x10000),(0x40000000,0x40000),(m.STOP,4096),(0x60000000,0x20000)]:u.mem_map(a,n)
def imp(name):
 a=0x10000000+len(handlers)*4;handlers[a]=name;return a
syms=m.load(u,Path('outputs/native-dmm-v28/candidate/yuy2_640_v28snap.so'),0x20000000,imp)
def hook(u,a,n,d):
 if a not in handlers:return
 name=handlers[a];r=[u.reg_read(x) for x in m.R]
 if name=='strchr':
  text=m.cstr(u,r[0]);i=text.find(chr(r[1]));v=r[0]+i if i>=0 else 0
 elif name=='sscanf':
  vals=m.cstr(u,r[0]).split()[:10]
  try:vals=[int(x,16) for x in vals]
  except ValueError:vals=[]
  if len(vals)!=10:v=0
  else:
   args=r[2:]+[m.word(u,u.reg_read(UC_ARM_REG_SP)+4*i) for i in range(8)]
   for p,value in zip(args,vals):m.put(u,p,value)
   v=10
 else:raise AssertionError(name)
 u.reg_write(UC_ARM_REG_R0,v);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
u.hook_add(UC_HOOK_CODE,hook)
def run(text):
 u.mem_write(0x40000000,text.encode()+b'\0');u.mem_write(0x40020000,bytes(8));u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,m.STACK);u.reg_write(UC_ARM_REG_LR,m.STOP)
 for r,v in zip(m.R,[0x40000000,614400,0x40020000]):u.reg_write(r,v)
 u.emu_start(syms['native_dmm_select_text'],m.STOP,count=1000000);assert u.reg_read(UC_ARM_REG_PC)==m.STOP
 return u.reg_read(UC_ARM_REG_R0),bytes(u.mem_read(0x40020000,8)).hex()
text=(O/'last-native-source-listing.txt').read_text();actual=run(text)
assert actual[0]==0 and int.from_bytes(bytes.fromhex(actual[1])[4:8],'little')==0x295,actual
checks=['captured streaming table selects native VEF type0x295']
for row,description in [
 ('408a 00000295 4 00 00 2 1 1 2a000000 001fa400','released allocation rejected'),
 ('408a 00000295 2 01 00 0 1 1 2a000000 001fa400','unopened allocation rejected'),
 ('408a 00000295 2 01 01 0 1 1 fe33a000 001fa400','MMIO alias rejected'),
 ('408a 00000295 2 01 01 0 1 1 3ffffff0 001fa400','DRAM span overflow rejected'),
 ('408a 00000295 2 01 01 0 1 1 2a000000 00095000','short span rejected'),
 ('408a 0000050f 2 01 01 0 1 1 18000000 001fa400','audio rejected'),
 ('408a 0000050e 2 01 01 0 1 1 18000000 001fa400','USB staging rejected'),
 ('408a 00000276 2 01 01 0 1 1 18000000 00320000','owned destination rejected')]:
 assert run(row+'\n')[0]==0xfffffffc,(row,description);checks.append(description)
legacy=run('408a 0006193f 2 01 01 0 1 1 18000000 001fa400\n');assert legacy[0]==0;checks.append('legacy explicit source remains supported')
report={'compiled_ARM_selector_executed':True,'passed':len(checks),'cases':checks,'captured_live_listing_result':'SELECTED_NATIVE_VEF_295','actual':actual,'camera_access':False}
Path('outputs/native-dmm-v28/selector-replay-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
