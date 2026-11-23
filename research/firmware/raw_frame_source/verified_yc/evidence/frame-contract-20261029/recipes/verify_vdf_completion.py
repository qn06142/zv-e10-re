from pathlib import Path
import json,struct
from rtos_harness import *
h=Harness();u=h.u
# Confirm selector/Activate/Execute slots using the original RTTI-linked vtables.
obj=MEM;msg=MEM+0x1000;vt=MEM+0x2000;calls=[]
vtable=0x64585008;h.put(obj,vtable)
h.run(h.word(vtable+12),obj,MEM+0x3000,MEM+0x3002)
selector=list(struct.unpack('<HH',u.mem_read(MEM+0x3000,4)));assert selector==[0x1000,0x8102]
h.put(msg,vt);h.put(vt+0x90,STOP+0x100|1)
def flag(a):calls.append(dict(value=a[1]));h.ret(0)
h.callbacks[STOP+0x100]=flag
assert h.run(h.word(vtable+16),obj,msg,MEM+0x4000)==0 and calls==[dict(value=1)]
h.calls.clear();assert h.run(h.word(vtable+20),obj,msg,MEM+0x4000)==0
assert h.calls==[] # two instruction leaf; no branch/call or DMM side effect
# ReleasePinAndMem has a DIFFERENT opcode selector.
release_vt=0x645823f8;h.put(obj,release_vt)
h.run(h.word(release_vt+12),obj,MEM+0x3000,MEM+0x3002)
release_selector=list(struct.unpack('<HH',u.mem_read(MEM+0x3000,4)));assert release_selector==[0x2001,0x050a]
out=dict(camera_access=False,original_rtti_vtables_and_virtual_methods_verified=True,sendcomp=dict(vtable=hex(vtable),selector=selector,activate_calls=calls,execute=hex(h.word(vtable+20)),execute_returns=0,execute_has_no_calls=True),release_pin_and_mem=dict(vtable=hex(release_vt),selector=release_selector,execute=hex(h.word(release_vt+20))),conclusion='VDF SystemCmdPinSendComp::Execute is a no-op. ReleasePinAndMem is command0x2001/0x050a, not0x1000/0x8102.',limitations=['Activation marks the message through a virtual setter; the broader scheduler may use that flag.','Does not prove all SEND_COMP handlers in all subsystems are no-ops.','No camera fault cause established.'])
Path('.local/outputs/yc-frame-contract-20261029/vdf-completion-vs-release.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
