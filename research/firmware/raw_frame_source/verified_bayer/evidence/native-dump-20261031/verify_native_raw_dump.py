from pathlib import Path
import sys,json,struct
sys.path.insert(0,str(Path('.local/work/yc-frame-contract-20261029').resolve()))
from rtos_harness import *
rows=[]
for gate,handle,err in [(0,0x1234,0),(1,0xffff,0),(1,0x1234,1),(1,0x1234,0)]:
 h=Harness();ev=[];h.callbacks[0x63d893f4]=lambda a:h.ret(gate);h.callbacks[0x6396f8c4]=lambda a:h.ret(0)
 def op(a):ev.append('open');h.put(a[3]+16,0x20000000);h.put(a[3]+20,0x2e6b000);h.ret(err)
 def dump(a):ev.append('dump');assert a[:4]==[1,0x20000000,0x2e6b000,7];h.ret(1)
 def close(a):ev.append('close');assert a[0]==handle;h.ret(0)
 h.callbacks.update({0x63d8a42a:op,0x63908820:dump,0x63d8a480:close})
 h.run(0x639088a0,1,handle,7)
 assert ev==([] if not gate or handle==0xffff else ['open'] if err else ['open','dump','close'])
 rows.append(dict(gate=gate,handle=hex(handle),open_error=err,calls=ev))
p=Path('.local/outputs/sensor-bayer-20261031/native-dump-ownership-tests.json');p.write_text(json.dumps(dict(original_instructions=True,camera_access=False,cases=rows,limitations='Dump service and resource lookup mocked; establishes call order and address/length forwarding only.'),indent=2));print('Passed four native dump open/write/close cases')
