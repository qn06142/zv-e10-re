from pathlib import Path
import sys,json,struct
sys.path.insert(0,str(Path('.local/work/yc-frame-contract-20261029').resolve()))
from rtos_harness import *
rows=[]
for status,kind in [(0,1),(0,2),(1,1)]:
 h=Harness();calls=[]
 def lookup(a):
  calls.append('lookup');h.u.mem_write(a[3]+8,struct.pack('<H',kind));h.put(a[3]+16,0x12340000);h.ret(status)
 def translate(a):calls.append('translate');assert a[0]==0x12340000 and a[1]==16;h.ret(0x23450000)
 h.callbacks.update({0x63970228:lookup,0x63c48e0c:translate,0x6396f8c4:lambda a:h.ret(0)})
 rc=h.run(0x63b31b14,MEM,0x1234)
 assert rc==(0x23450000 if status==0 and kind==1 else 0xffffffff)
 assert ('translate' in calls)==(status==0 and kind==1)
 rows.append(dict(lookup_status=status,span_kind=kind,result=hex(rc),calls=calls))
p=Path('.local/outputs/sensor-bayer-20261030');(p/'handle-resolution-tests.json').write_text(json.dumps(dict(original_instructions=True,camera_access=False,cases=rows,limitations='Lookup and address translation mocked; no live handle replay.'),indent=2))
with (p/'REPORT.md').open('a') as f:f.write('''
## Follow-up: handle resolution and submission boundary

Traced0x63b31b14: queries native resource lookup0x63970228 with class5, requires span field+8==1, translates address field+16 via0x63c48e0c(address,16), otherwise returns0xffffffff. Three original-instruction cases verify lookup failure, unsupported span kind and success. This is resource-handle resolution, not a scan for Bayer signatures.

Start tail0x63b32704..0x63b3274c copies parameter geometry into the resolved resource state and sets fixed0x80/0x80/1 fields. It constructs two additional state blocks, then invokes0x63df189e with operation4 and mailbox/result pointers. Returning from this call and immediately releasing in the native caller requires tracing that call's synchronization; do not assume a successful start means pixels are complete.

The caller's initial0x6390897c invocation opens an existing handle passed in r1 and reads/copies metadata; it does not by itself establish where sensor pixels are allocated. A separate conditional allocation uses unit0x1df in that helper. Buffer role and sensor-source origin remain unresolved. No guessed RAW patch built or live command sent.
''')
print('Passed three original-instruction handle-resolution cases; follow-up evidence saved.')
