from pathlib import Path
import sys,json,struct
sys.path.insert(0,str(Path('.local/work/yc-frame-contract-20261029').resolve()))
from rtos_harness import *
rows=[]
for existing,unit,error in [(0xffff,0x50505,0),(0xffff,0x5056e,0),(0xffff,0x236,0),(0xffff,0x50505,1),(0xffff,0,0),(0x3456,0x50505,0)]:
 h=Harness();ctx=MEM;calls=[];h.u.mem_write(ctx+0x67b6,struct.pack('<H',existing))
 h.callbacks[0x638d9fb8]=lambda a:(calls.append('select'),h.ret(unit))
 h.callbacks[0x6396f8c4]=lambda a:h.ret(0)
 def alloc(a):
  calls.append('allocate');assert a[:3]==[unit,1,0xffffffff]
  h.u.mem_write(a[3]+4,struct.pack('<H',0x1234));h.put(a[3]+16,0x20000000);h.put(a[3]+20,0x3000000);h.ret(error)
 h.callbacks[0x6390c348]=alloc
 rc=h.run(0x638d9ff4,ctx)
 ok=existing==0xffff and unit and not error
 assert rc==(0x1234 if ok else existing)
 if ok:assert h.word(ctx+0x6b58)==unit and h.word(ctx+0x6b5c)==0x20000000 and h.word(ctx+0x6b60)==0x3000000
 if existing!=0xffff:assert not calls
 rows.append(dict(function='allocation',existing=hex(existing),unit=hex(unit),allocator_error=error,rc=hex(rc),calls=calls))
for err,n in [(0,0),(0,1),(0,2),(1,0)]:
 h=Harness();out=MEM+0x1000;events=[];h.callbacks[0x63d94468]=lambda a:h.ret(0)
 def lookup(a):
  assert a[:3]==[0x1234,0,0xffffffff] and h.word(h.u.reg_read(UC_ARM_REG_SP))==5
  events.append('lookup');h.u.mem_write(a[3]+8,struct.pack('<H',n));h.ret(err)
 h.callbacks[0x63970228]=lookup
 rc=h.run(0x63d8a42a,0x1234,0,0xffffffff,out);assert rc==err
 rows.append(dict(function='open',lookup_error=err,span_count=n,rc=rc))
p=Path('.local/outputs/sensor-bayer-20261030/followup');(p/'allocation-open-tests.json').write_text(json.dumps(dict(original_instructions=True,camera_access=False,cases=rows,limitations=['Selector/allocator/native lookup mocked. Confirms storage and error handling, not physical capacity or RAW production.']),indent=2));print('Passed',len(rows),'allocation/open cases')
