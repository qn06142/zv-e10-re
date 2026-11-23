from pathlib import Path
import sys,json
sys.path.insert(0,str(Path('.local/work/yc-frame-contract-20261029').resolve()))
from rtos_harness import *
rows=[]
for count,fail in [(1,False),(2,False),(1,True),(4,False)]:
 h=Harness();ids=MEM;out=MEM+0x100;flags=MEM+0x200;events=[];h.u.mem_write(ids,b'\x04\x07\x09')
 h.callbacks[0x6396f8c4]=lambda a:h.ret(0)
 def receive(a):
  i=len(events);events.append(a[1]);sp=h.u.reg_read(UC_ARM_REG_SP)
  h.u.mem_write(a[2],bytes([i+1])*16);h.u.mem_write(a[3],b'\x01');h.u.mem_write(h.word(sp),bytes([4 if i==0 else 7]));h.ret(2 if fail else 0)
 h.callbacks[0x63b31828]=receive
 rc=h.run(0x63b318ec,MEM+0x300,ids,out,flags,count)
 assert rc==(6 if count>3 else 1 if fail else 0)
 assert len(events)==(0 if count>3 else 1 if fail else count)
 if not fail and count<=3:assert bytes(h.u.mem_read(out,16))==bytes([1])*16
 rows.append(dict(responses_requested=count,receive_error=fail,rc=rc,receive_commands=events))
p=Path('.local/outputs/sensor-bayer-20261030');(p/'response-wait-tests.json').write_text(json.dumps(dict(original_instructions=True,camera_access=False,cases=rows,limitations='Receive service mocked; response0x41 semantics are not yet proven to mean pixel DMA completion.'),indent=2))
with (p/'REPORT.md').open('a') as f:f.write('''
## Follow-up: start waits for a response, not yet proved pixel completion

0x63df189e forces response-count1 and calls0x63b31990. That routine submits through0x63b31358, then invokes0x63b318ec. The latter receives command0x41 via0x63b31828, matches returned ID to requested ID, copies16 response bytes and one flag, and returns after the requested number of responses. Four original-instruction cases verify one/two responses, receive failure and count>3 rejection. Hardware/message receive mocked. This disproves an immediate fire-and-forget return, but command0x41 may acknowledge setup rather than completed pixels; do not call it a DMA fence until its producer is traced. Next trace0x63b31828 and producer of0x41.
''')
print('Passed four response-wait original-instruction cases.')
