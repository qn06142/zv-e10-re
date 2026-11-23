from pathlib import Path
import sys,json,struct
sys.path.insert(0,str(Path('.local/work/yc-frame-contract-20261029').resolve()))
from rtos_harness import *
O=Path('.local/outputs/sensor-bayer-20261030');cases=[]
def common():
 h=Harness()
 for f in [0x63d20228,0x63d20248,0x63df15da,0x6396f8c4]:h.callbacks[f]=lambda a:h.ret(0)
 h.callbacks[0x63d20260]=lambda a:h.ret(7)
 return h
for claim,alloc_error,reserve_error in [(0,0,0),(1,0,0),(0,1,0),(0,0,2),(1,0,2)]:
 h=common();events=[];request=MEM;sel=MEM+0x100;out=MEM+0x200
 h.u.mem_write(request,bytes([claim]));h.u.mem_write(sel,b'\x03')
 def reserve(a):events.append(['reserve',a[2]]);h.ret(reserve_error)
 def configure(a):events.append(['claim',a[1],a[2]]);h.ret(0)
 def alloc(a):events.append(['allocate_resource']);h.u.mem_write(a[1],struct.pack('<H',0x1234));h.ret(alloc_error)
 def unwind(a):events.append(['undo_reserve',a[1],a[2]]);h.ret(0)
 h.callbacks.update({0x63df188c:reserve,0x63b31518:configure,0x63b3120c:alloc,0x63df1872:unwind})
 rc=h.run(0x63b322a0,request,sel,out)
 assert rc==(reserve_error if reserve_error else 2 if alloc_error else 0)
 assert events[0]==['reserve',4]
 if reserve_error:assert len(events)==1
 elif alloc_error:assert events[-1]==['undo_reserve',3,4]
 else:assert struct.unpack('<H',h.u.mem_read(out,2))[0]==0x1234
 cases.append(dict(function='acquire',claim=claim,alloc_error=alloc_error,reserve_error=reserve_error,rc=rc,calls=events))
for optional,bad in [(False,False),(True,False),(True,True)]:
 h=common();events=[];param=MEM+0x400
 fields=[0x18,0x1a,0x30,2,0x40,0x42]
 for i,off in enumerate(fields):h.u.mem_write(param+off,struct.pack('<H',0x1100+i))
 if not optional:h.u.mem_write(param+0x42,b'\xff\xff')
 def close(a):events.append(['release_handle',a[1]]);h.ret(1 if bad and a[1]==0x1102 else 0)
 def free(a):events.append(['release_resource',a[1]]);h.ret(0)
 def unreserve(a):events.append(['undo_reserve',a[1],a[2]]);h.ret(0)
 h.callbacks.update({0x63df19e2:close,0x63df16aa:free,0x63df1872:unreserve})
 rc=h.run(0x63b32344,3,0x1234,param)
 expected=[0x1100,0x1101,0x1102,0x1103,0x1104]+([0x1105] if optional else [])
 assert [e[1] for e in events if e[0]=='release_handle']==expected
 assert events[-1]==['undo_reserve',3,4] and rc==(2 if bad else 0)
 assert ['release_resource',0x1234] in events
 cases.append(dict(function='release',optional_handle=optional,handle_release_failure=bad,rc=rc,calls=events))
report=dict(camera_access=False,original_ARM_instructions_executed=True,cases=cases,limitations=['Resource service, lock and hardware callbacks are mocked. Tests establish call order, rollback and parameter offsets only; no sensor pixel capture or DMA completion is simulated.'])
(O/'resource-contract-tests.json').write_text(json.dumps(report,indent=2));print('Passed',len(cases),'original-instruction acquire/release cases')
