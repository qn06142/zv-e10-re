"""Execute cited codec OPEN diagnostic function with logging stubs; not initialization or dispatch."""
from pathlib import Path
import sys,json
sys.path.insert(0,'.local/work/yc-frame-contract-20261029')
from rtos_harness import *
from rtos import cstr
h=Harness();u=h.u;obj=MEM;ctx=MEM+0x1000;request=MEM+0x2000;logs=[]
h.put(obj,ctx);h.put(ctx,ctx+0x100)
h.put(request+0x38,1);h.put(request+0x50,1);h.put(request+0x54,2);h.put(request+0x58,3)
h.callbacks[0x63a062f0]=lambda a:h.ret(0)
h.callbacks[0x63c602be]=lambda a:h.ret(0)
def log(a):
 sp=u.reg_read(UC_ARM_REG_SP);fmt=cstr(h.word(sp+0x10));logs.append({'format':fmt,'arg0':h.word(sp+0x14)})
 h.ret(0)
h.callbacks[0x63daee88]=log
h.run(0x6368cffc,obj,request)
for needle,value in [('input_image_bit_depth',1),('input_image_compress',2),('input_image_chroma',3)]:
 rows=[x for x in logs if needle in x['format']];assert len(rows)==1 and rows[0]['arg0']==value,(needle,rows)
out={'camera_access':False,'original_diagnostic_function_executed':True,'field_offset_controls_verified':{'0x50':'input_image_bit_depth','0x54':'input_image_compress','0x58':'input_image_chroma'},'logged_fields':logs,'limitations':['Logging/time/log-context calls mocked; no IPC or hardware invoked.','This function dumps an existing request. It does not prove builder assignments, enum meanings, producer precision or OPEN routing.']}
Path('.local/outputs/yc-high-depth-review-20261030/open-diagnostic-verification.json').write_text(json.dumps(out,indent=2));print('Verified original diagnostic function and3field offsets; rows',len(logs))

