"""Identify native receiver/dispatcher by original constructor prefixes and RTTI."""
from pathlib import Path
import runpy,json,contextlib,io
with contextlib.redirect_stdout(io.StringIO()): c=runpy.run_path(str(Path(__file__).parent/'verify_category2_and_pin.py'))
u=c['u'];run=c['run'];word=c['word'];cstr=c['cstr'];MEM=c['MEM'];BASE=0x18000000
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *
stop_at=None

def stop_prefix(u,pc,size,data):
 if pc==stop_at:u.reg_write(UC_ARM_REG_PC,c['STOP'])
u.hook_add(UC_HOOK_CODE,stop_prefix)
objects=[]
for start,stop in [(0x7009a0,0x7009ba),(0x700734,0x700746)]:
 stop_at=BASE+stop
 u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,c['STACK']);u.reg_write(UC_ARM_REG_LR,c['STOP']);u.reg_write(UC_ARM_REG_R0,MEM+0x5000)
 u.emu_start(BASE+start+1,c['STOP'],count=1000)
 assert u.reg_read(UC_ARM_REG_PC)==c['STOP']
 vt=word(MEM+0x5000);objects.append(dict(constructor=hex(start),stopped_before=hex(stop),rtti=cstr(word(word(vt-4)+4)),vtable_relative=hex(vt-BASE)))
result=dict(camera_access=False,original_constructor_prefixes_executed=True,full_constructors_not_executed=True,objects=objects,receive_loop='libObj.so+0x700a2c',dispatch='libObj.so+0x7007d8',limitations=['RTTI identifies objects; it does not prove an authorized live video endpoint.','No OSAL transport, sysconf, DMM, or camera hardware executed.'])
Path('.local/outputs/yc-subsystem-offline-20261029/native-receiver-rtti.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
