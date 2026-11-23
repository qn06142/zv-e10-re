"""Execute native type-1 opcode switch; stop before side effects/abort."""
from pathlib import Path
import runpy,json,contextlib,io,struct
with contextlib.redirect_stdout(io.StringIO()): c=runpy.run_path(str(Path(__file__).parent/'verify_category2_and_pin.py'))
u=c['u'];MEM=c['MEM'];BASE=0x18000000
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *
expected={0x100:0x6f7070,0x8100:0x6f70ac,0x102:0x6f7124,0x8102:0x6f712c};records=[];visited=[];caught=None

def trace(u,pc,size,data):
 global caught
 if pc==BASE+0x6fbdf8:
  u.reg_write(UC_ARM_REG_R0,0);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR));return
 if pc in [BASE+x for x in expected.values()]:visited.append(pc-BASE)
 if pc==BASE+0x10b888:
  caught='abort PLT reached';u.reg_write(UC_ARM_REG_PC,c['STOP'])
 elif pc in [BASE+0x6f7070,BASE+0x6f70ac]:
  caught='connection wrapper reached; stopped before operation';u.reg_write(UC_ARM_REG_PC,c['STOP'])
u.hook_add(UC_HOOK_CODE,trace)
for opcode,target in expected.items():
 visited.clear();caught=None;u.mem_write(MEM+0x6000,struct.pack('<HH',0x1000,opcode)+bytes(60))
 u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,c['STACK']);u.reg_write(UC_ARM_REG_LR,c['STOP'])
 for reg,arg in [(UC_ARM_REG_R0,MEM+0x5000),(UC_ARM_REG_R1,MEM+0x6000),(UC_ARM_REG_R2,0),(UC_ARM_REG_R3,0)]:u.reg_write(reg,arg)
 u.emu_start(BASE+0x6f71e9,c['STOP'],count=10000)
 assert u.reg_read(UC_ARM_REG_PC)==c['STOP'] and visited==[target] and caught
 records.append(dict(opcode=hex(opcode),branch_target=hex(target),outcome=caught))
out=dict(camera_access=False,original_switch_and_abort_wrappers_executed=True,entry='libObj.so+0x6f71e8 Thumb',records=records,conclusion='The type-1 native handler connected to YC1Pin accepts connect/control paths but unconditionally calls abort for PIN_SEND and PIN_SEND_COMP; it is not a drop-in frame receiver.',limitations=['No real OSAL messages or producer registration used.','Other endpoints may receive frames; this does not prove no receive endpoint exists.'])
Path('.local/outputs/yc-subsystem-offline-20261029/native-type1-dispatch-execution.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
