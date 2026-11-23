from pathlib import Path
import sys,json
sys.path.insert(0,str(Path('.local/work/yc-frame-contract-20261029').resolve()))
from rtos_harness import *
rows=[]
for op in range(8):
 h=Harness();events=[];h.callbacks[0x63d94468]=lambda a:h.ret(0)
 def setflag(a):events.append(a[:2]);h.ret(0)
 h.callbacks[0x635df194]=setflag
 mask=h.run(0x63d8913a,op)
 h.run(0x63d89118,0,op)
 assert events==[[0x16,mask]] and mask==0x40000<<op
 rows.append(dict(operation=op,mask=hex(mask),callback_event=events))
for results in [[0],[-50,0],[-5]]:
 h=Harness();calls=[];pending=iter(results)
 def wait(a):
  timeout=h.word(h.u.reg_read(UC_ARM_REG_SP));calls.append(dict(event=a[0],mask=hex(a[1]),mode=a[2],timeout=hex(timeout)));h.put(a[3],0x40000);h.ret(next(pending))
 h.callbacks[0x635df1cc]=wait
 for f in [0x6396f8c4,0x637a71f4,0x63d29e74,0x63d2324a,0x63d08e86,0x635df1b0,0x63d94468]:h.callbacks[f]=lambda a:h.ret(0)
 rc=h.run(0x63906dbc,0x40000,1)
 assert rc==(0xffffffff if len(results)>1 else 0xbb8) and len(calls)==len(results)
 assert calls[0]==dict(event=0x16,mask='0x40000',mode=0,timeout='0xbb8')
 if len(calls)>1:assert calls[1]['timeout']=='0xffffffff'
 rows.append(dict(wait_results=results,returned=hex(rc),waits=calls))
p=Path('.local/outputs/sensor-bayer-20261030/followup/dfe-completion-bridge-tests.json');p.write_text(json.dumps(dict(original_instructions=True,camera_access=False,cases=rows,limitations=['Event system/recovery calls mocked; tests establish matching masks and wrapper behavior, not the hardware completion fact triggering callback.']),indent=2));print('Passed',len(rows),'native DFE mask/callback/wait cases')


