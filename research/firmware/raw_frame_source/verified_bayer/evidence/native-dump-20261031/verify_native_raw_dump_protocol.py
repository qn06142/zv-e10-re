from pathlib import Path
import sys,json
sys.path.insert(0,str(Path('.local/work/yc-frame-contract-20261029').resolve()))
from rtos_harness import *
rows=[]
for send_error,receive_error,busy in [(0,0,0),(1,0,0),(0,1,0),(0,0,1)]:
 h=Harness();events=[];msg=MEM+0x1000;reply=MEM+0x2000
 h.u.mem_write(0x6396f368+4+0xbb0ce4,bytes([busy]))
 for f in [0x6396f2b8,0x6396f28c,0x6396f2ec,0x63d943d8]:h.callbacks[f]=lambda a:h.ret(0)
 h.callbacks[0x6396e118]=lambda a:h.ret(5)
 def allocate(a):assert a[0]==0x12802f1 and a[2]==24;events.append('allocate');h.put(a[1],msg);h.ret(0)
 def service(a):
  if a[0]==0x2a:h.put(a[2],0x777)
  h.ret(0)
 def send(a):events.append(dict(send_queue=hex(a[0]),message=bytes(h.u.mem_read(a[1],24)).hex()));h.ret(send_error)
 def receive(a):events.append(dict(wait_queue=hex(a[0]),timeout=a[2]));h.put(a[1],reply);h.ret(receive_error)
 h.callbacks.update({0x635df710:allocate,0x635df764:service,0x635df64c:send,0x635df6a0:receive,0x635df72c:lambda a:h.ret(0)})
 rc=h.run(0x6396f33c,0x701,0x20000000,4096,0)
 if busy:assert rc==0xfffffffd and not events
 else:
  sent=next(x for x in events if isinstance(x,dict) and 'message'in x);b=bytes.fromhex(sent['message']);assert b[:12]==bytes.fromhex('010001070000002000100000')
  assert any(isinstance(x,dict) and x.get('timeout')==300000 for x in events)
  assert rc==(0xfffffffc if send_error or receive_error else 0)
 rows.append(dict(send_error=send_error,receive_error=receive_error,busy=busy,rc=hex(rc),events=events))
p=Path('.local/outputs/sensor-bayer-20261031/native-dump-protocol-tests.json');p.write_text(json.dumps(dict(original_instructions=True,camera_access=False,cases=rows,limitations='Message pool/send/receive/release/logging mocked. Receiver durability and pixel validity not proved.'),indent=2));print('Passed four native dump protocol cases')

