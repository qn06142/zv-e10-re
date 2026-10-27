from pathlib import Path
import importlib.util,struct,json,subprocess
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
ROOT = Path(r'D:/02_Development_And_Projects/pmca-re')
OUT = Path(r'C:/Users/qn061/Documents/Codex/2026-10-22/chec/outputs/yc-source-re-20261025') if not Path('outputs/yc-source-re-20261025').is_dir() else Path('outputs/yc-source-re-20261025')
WORK = Path(__file__).resolve().parent
subprocess.run(['C:/msys64/ucrt64/bin/arm-none-eabi-gcc.exe','-mcpu=cortex-a5','-marm','-mfloat-abi=soft','-O2','-fPIC','-fno-builtin','-fno-stack-protector','-nostdlib','-shared','-Wl,--no-undefined,--hash-style=sysv','-o',str(OUT/'sony_yc_pin_wire.so'),str(WORK/'sony_yc_pin_wire.c')],check=True)
spec=importlib.util.spec_from_file_location('support',ROOT/'research/firmware/yuy2_transport_v25/verify_support.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
u=Uc(UC_ARCH_ARM,UC_MODE_ARM);handlers={};captured=[];calls=[]
for a,n in [(0x10000000,0x10000),(0x40000000,0x10000),(m.STOP,4096),(0x60000000,0x20000)]:u.mem_map(a,n)
def imp(name):
 at=0x10000000+len(handlers)*4;handlers[at]=name;return at
sdk=m.load(u,ROOT/'dumps/camera_2025/usr/usr/lib/dataflowInfraFramework.so',0x08000000,imp)
ours=m.load(u,OUT/'sony_yc_pin_wire.so',0x20000000)
def hook(u,a,n,d):
 if a not in handlers:return
 name=handlers[a];r=[u.reg_read(x) for x in m.R];calls.append(name)
 if name=='_ZN18_MSG_PIN_SEND_COMPC1Ev':u.reg_write(UC_ARM_REG_PC,sdk[name]);return
 if 'DataflowInfraMsgC1Ev' in name or 'DataflowInfraMsgD1Ev' in name:value=r[0]
 elif 'DataflowInfraMsg14SetDataflowMsg' in name:captured.append(bytes(u.mem_read(r[1],r[2])));value=0
 elif 'DataflowInfraMsg10SetReplyId' in name or 'DataflowInfraMsg8SetSrcId' in name:assert r[1]==0x123456;value=0
 elif 'DataflowInfraSender9SendASync' in name:assert r[1]==0x0059000e;value=0
 else:raise AssertionError((name,[hex(x) for x in r]))
 u.reg_write(UC_ARM_REG_R0,value);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
u.hook_add(UC_HOOK_CODE,hook)
def run(address,*args):
 u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,m.STACK);u.reg_write(UC_ARM_REG_LR,m.STOP)
 for r,v in zip(m.R,args):u.reg_write(r,v&0xffffffff)
 u.emu_start(address,m.STOP,count=50000);assert u.reg_read(UC_ARM_REG_PC)==m.STOP;return u.reg_read(UC_ARM_REG_R0)
pin=0x40000000;source=struct.pack('<4I',0,2,0,0x0059000e);dest=struct.pack('<4I',0,1,0,0x00123456)
u.mem_write(pin+8,source);u.mem_write(pin+24,dest);u.mem_write(pin+4,struct.pack('<I',0x40003000));u.mem_write(pin+0x28,struct.pack('<I',0))
# Actual SDK SendComp's pin direction is INPUT (1); it retains logical output/input order.
assert run(sdk['_ZN16DataflowInfraPin8SendCompEl'],pin,-7)==0
assert len(captured)==1
expected=struct.pack('<4H',0x1000,0x8102,0x2c,1)+source+dest+struct.pack('<i',-7)
assert captured[0]==expected,(captured[0].hex(),expected.hex())
# Actual SDK SEND constructor establishes header; populate only native documented fields.
wire=0x40001000
run(sdk['_ZN13_MSG_PIN_SENDC1Ev'],wire)
raw=bytearray(u.mem_read(wire,0x34));raw[8:24]=source;raw[24:40]=dest;struct.pack_into('<IHHI',raw,40,0x11223344,0x1234,0,0x55667788);u.mem_write(wire,bytes(raw))
frame=0x40002000;ack=0x40004000
assert run(ours['sony_pin_decode_send'],wire,0x34,frame)==0
assert run(ours['sony_pin_make_complete'],frame,-7,ack,0x2c)==0
assert bytes(u.mem_read(ack,0x2c))==captured[0]
checks=['native SEND header matches executed Sony constructor','completion bytes match executed Sony SendComp including property direction/order and negative status']
for n in range(0x34):
 u.mem_write(frame,b'\xa5'*44);assert run(ours['sony_pin_decode_send'],wire,n,frame)==0xffffffff;assert bytes(u.mem_read(frame,44))==b'\xa5'*44
for off,value in [(0,0x400),(2,0x2),(4,0x40),(6,0)]:
 changed=bytearray(raw);struct.pack_into('<H',changed,off,value);u.mem_write(wire,bytes(changed));assert run(ours['sony_pin_decode_send'],wire,0x34,frame)==0xffffffff
checks.append('all52 truncated SEND lengths and four invalid header fields rejected')
report={'passed':checks,'SDK_SendComp_executed':True,'OSAL_IPC_executed':False,'camera_access':False,'native_complete_hex':expected.hex(),'imports_intercepted':sorted(set(calls)), 'Sony_imports_forwarded_to_original_code':['_ZN18_MSG_PIN_SEND_COMPC1Ev'], 'external_functions_stubbed':sorted(set(calls)-{'_ZN18_MSG_PIN_SEND_COMPC1Ev'})}
(OUT/'pin-wire-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
