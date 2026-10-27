from pathlib import Path
import importlib.util,struct,json,subprocess
from unicorn import *
from unicorn.arm_const import *
R=Path(r'D:/02_Development_And_Projects/pmca-re');W=Path('work/native-dmm-callback/recipe');O=Path('outputs/native-dmm-callback')
subprocess.run(['C:/msys64/ucrt64/bin/arm-none-eabi-gcc.exe','-mcpu=cortex-a5','-marm','-mfloat-abi=soft','-O2','-fPIC','-fno-builtin','-fno-stack-protector','-nostdlib','-shared','-Wl,-Bsymbolic,--no-undefined,--hash-style=sysv','-o',str(O/'wire.so'),str(W/'native_dmm_wire.c')],check=True)
spec=importlib.util.spec_from_file_location('support',R/'research/firmware/yuy2_transport_v26_raw/verify_support.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
u=Uc(UC_ARCH_ARM,UC_MODE_ARM);handlers={};sent=[];calls=[]
for a,n in [(0x10000000,0x10000),(0x40000000,0x10000),(m.STOP,4096),(0x60000000,0x20000)]:u.mem_map(a,n)
def imp(name):
 a=0x10000000+len(handlers)*4;handlers[a]=name;return a
sdk=m.load(u,R/'dumps/camera_2025/usr/usr/lib/libBizFw.so',0x08000000,imp);ours=m.load(u,O/'wire.so',0x20000000)
Q=0x12345678;HANDLE=0x408a;TYPE=0x6193f

def hook(u,a,n,d):
 if a not in handlers:return
 name=handlers[a];r=[u.reg_read(x) for x in m.R];calls.append(name)
 if name=='memset':u.mem_write(r[0],bytes([r[1]&255])*r[2]);v=r[0]
 elif 'sndAsyncGlobalMsg' in name:
  assert r[2]==24 and r[3]==Q and struct.unpack('<I',u.mem_read(u.reg_read(UC_ARM_REG_SP),4))[0]==0x61003c
  sent.append(bytes(u.mem_read(r[1],24)));v=0
 elif 'rcvAsyncGlobalMsg' in name:
  assert r[2]==24 and r[3]==Q
  raw=bytearray(24);struct.pack_into('<4H',raw,0,struct.unpack_from('<H',sent[-1])[0]|0x8000,0,HANDLE,Q&65535);u.mem_write(r[1],bytes(raw));v=0
 elif 'Dmm' in name or 'Print' in name or 'Debug' in name or 'AvbbcBaseClassLog' in name:
  # Logging only; reject any unrecognized executable service.
  if 'DmmCh' in name:raise AssertionError(name)
  v=0
 else:raise AssertionError((name,[hex(x) for x in r]))
 u.reg_write(UC_ARM_REG_R0,v);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
u.hook_add(UC_HOOK_CODE,hook)
def run(addr,*args):
 u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,m.STACK);u.reg_write(UC_ARM_REG_LR,m.STOP)
 for r,v in zip(m.R,args):u.reg_write(r,v&0xffffffff)
 for i,v in enumerate(args[4:]):u.mem_write(m.STACK+i*4,struct.pack('<I',v&0xffffffff))
 u.emu_start(addr,m.STOP,count=100000);assert u.reg_read(UC_ARM_REG_PC)==m.STOP;return u.reg_read(UC_ARM_REG_R0)
obj=0x40000000;reply=0x40001000;raw=0x40002000
u.mem_write(obj+4,struct.pack('<IH',Q,1));rows=[]
for cmd,name,args in [(2,'allocShare',(TYPE,HANDLE,0)),(5,'4openE',(HANDLE,0,0)),(6,'5closeE',(HANDLE,)),(4,'4freeE',(HANDLE,0))]:
 symbol=next(n for n in sdk if '5DmmCh' in n and name in n)
 assert run(sdk[symbol],obj,reply,*args)==0
 actual=sent[-1];run(ours['native_dmm_request'],raw,cmd,TYPE,HANDLE,Q)
 expected=bytes(u.mem_read(raw,24));assert actual==expected,(cmd,actual.hex(),expected.hex())
 rows.append({'command':cmd,'native_symbol':symbol,'native_wire_hex':actual.hex(),'matches_compiled_encoder':True})
report={'actual_Sony_methods_executed':True,'hardware_services_mocked':True,'camera_access':False,'requests':rows,'intercepted_imports':sorted(set(calls))}
(O/'wire-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

