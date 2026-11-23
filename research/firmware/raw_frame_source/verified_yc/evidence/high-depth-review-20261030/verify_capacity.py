"""Execute original decoder capacity-bucket arithmetic; no camera or hardware calls."""
from pathlib import Path
import sys,struct,json
sys.path.insert(0,'.local/work/yc-frame-contract-20261029')
from rtos_harness import *
rows=[]
for depth in [0,1]:
 for w,hgt in [(1920,1080),(1921,1080),(2560,2025),(2560,2026),(3840,2160),(3840,2161)]:
  h=Harness();u=h.u;obj=MEM;config=MEM+0x10000;calc=[];rejected=[]
  h.put(config+0x38,depth)
  h.callbacks[0x63da5ca8]=lambda a:h.ret(config)
  h.callbacks[0x639f50c8]=lambda a:calc.append(a[0])
  h.callbacks[0x639f5104]=lambda a:u.reg_write(UC_ARM_REG_PC,STOP)
  def reject(a):rejected.append(True);u.reg_write(UC_ARM_REG_PC,STOP)
  h.callbacks[0x639f5150]=reject
  u.reg_write(UC_ARM_REG_R4,obj);u.reg_write(UC_ARM_REG_R5,w);u.reg_write(UC_ARM_REG_R6,config);u.reg_write(UC_ARM_REG_R7,hgt)
  h.run(0x639f506e,balanced=False)
  assert calc==[w*hgt],(depth,w,hgt,calc)
  expected=0x36a if w*hgt<=0x1fa400 else 0x3d0 if w*hgt<=0x4f1a00 else 0x369 if w*hgt<=0x7e9000 else None
  assert bool(rejected)==(expected is None)
  got=h.word(obj+0x45c00) if expected is not None else None
  assert got==expected,(depth,w,hgt,got,expected)
  rows.append(dict(bit_depth=depth,width=w,height=hgt,original_calculated_value=calc[0],selected_pool_or_unit_id=hex(got) if got is not None else None,oversize=bool(rejected)))
result=dict(camera_access=False,original_instructions_executed=True,division_helper_original=True,only_mocked_call='0x63da5ca8 returns a controlled configuration object',cases=rows,conclusion='For both depths0and1 this block compares width*height against three bucket constants and selects0x36a/0x3d0/0x369. The constants do not prove 2.5/4 bytes per pixel, packing order, or association with output mode4/5.')
Path('.local/outputs/yc-high-depth-review-20261030/capacity-buckets-verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
