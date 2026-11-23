from pathlib import Path
import json,struct
from rtos_harness import *
h=Harness();u=h.u;rows=[]
def record(a):rows.append(dict(object=hex(a[0]),properties=list(struct.unpack('<4I',u.mem_read(a[1],16))),sender=hex(a[2])))
h.callbacks[0x63ac1a48]=record
assert h.run(0x63744f2c)==0
assert len(rows)==12
vdf=rows.copy();rows.clear()
h.put(MEM+0x1000+8,0x00570050)
assert h.run(0x6364e6c8,MEM,MEM+0x1000,0,0)==MEM
assert len(rows)==7
mc=rows.copy()
out=dict(camera_access=False,original_constructor_and_initialization_code_executed=True,external_calls_mocked=False,rtos_reference_md5=hashlib.md5(DATA).hexdigest(),vdf_pins=vdf,encoder_pins=mc,property_order=['type (0 used for YC)','direction (1 input,2 output,3 bidirectional control)','pin index','OSAL queue'],limitations=['Encoder queue is a fixture input, not a recovered active runtime connection.','VDF input table fields are reordered by initialization; do not use raw table rows as PIN_PROPERTY.','These constructors do not request a new live connection.'])
Path('.local/outputs/yc-frame-contract-20261029/original-pin-initialization.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
