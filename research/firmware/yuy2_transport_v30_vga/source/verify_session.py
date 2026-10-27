from pathlib import Path
import importlib.util,struct,json
from unicorn import *
from unicorn.arm_const import *
spec=importlib.util.spec_from_file_location('support',Path(__file__).parent/'recipe/verify_support.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
u=Uc(UC_ARCH_ARM,UC_MODE_ARM);handlers={};calls=[]
for a,n in [(0x10000000,0x10000),(m.STOP,4096),(0x60000000,0x20000)]:u.mem_map(a,n)
def imp(name):
 a=0x10000000+len(handlers)*4;handlers[a]=name;return a
syms=m.load(u,Path('outputs/vga-v30/build/yuy2_640_v30vga.so'),m.MB,imp)
def hook(u,a,n,d):
 if a not in handlers:return
 name=handlers[a];calls.append(name)
 if name=='snprintf':v=0
 elif name=='open':v=-1
 else:raise AssertionError('unexpected camera/SDK call: '+name)
 u.reg_write(UC_ARM_REG_R0,v&0xffffffff);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
u.hook_add(UC_HOOK_CODE,hook)
def run(name,arg):
 u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,m.STACK);u.reg_write(UC_ARM_REG_LR,m.STOP);u.reg_write(UC_ARM_REG_R0,arg)
 u.emu_start(syms[name],m.STOP,count=10000);assert u.reg_read(UC_ARM_REG_PC)==m.STOP;assert u.reg_read(UC_ARM_REG_SP)==m.STACK
 return u.reg_read(UC_ARM_REG_R0)
m.put(u,syms['output_session_closed'],1);assert run('ensure_source',0x1234)==41;assert not calls
m.put(u,syms['output_session_closed'],0);m.put(u,syms['pixels'],0x41000000)
assert run('detach_source',0x1234)==0
assert m.word(u,syms['output_session_closed'])==1
assert not m.word(u,syms['shared_running'])
assert run('ensure_source',0x1234)==41
assert m.word(u,syms['pixels'])==0x41000000
report={'camera_access':False,'compiled_ARM_module_executed':True,'passed':['closed-session rebind rejected before any SDK access','stop before first host capture still closes session','retained output mapping not written or reused'],'only_mocked':sorted(set(calls))}
Path('outputs/vga-v30/session-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
