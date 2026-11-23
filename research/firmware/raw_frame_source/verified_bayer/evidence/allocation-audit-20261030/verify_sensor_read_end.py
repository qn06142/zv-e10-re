from pathlib import Path
import sys,json
sys.path.insert(0,str(Path('.local/work/yc-frame-contract-20261029').resolve()))
from rtos_harness import *
rows=[]
for status,bits in [(0,0x2000),(0,0x8000),(0,0x4000),(0,0x100000),(1,0)]:
 h=Harness();events=[];h.callbacks[0x63d79948]=lambda a:h.ret(MEM)
 for f in [0x63d8943e,0x6396f8c4,0x63d94468]:h.callbacks[f]=lambda a:h.ret(0)
 def wait(a):
  assert a[:3]==[0x15,0x10e000,1] and h.word(h.u.reg_read(UC_ARM_REG_SP))==0xffffffff
  events.append('wait');h.put(a[3],bits);h.ret(status)
 def clear(a):events.append('clear');assert a==[0x15,0xffef1fff,a[2],a[3]];h.ret(0)
 h.callbacks[0x635df1cc]=wait;h.callbacks[0x635df1b0]=clear
 for f,name in [(0x63d89352,'set_stage20'),(0x63d86eb6,'helper_6eb6'),(0x63d86e46,'helper_6e46'),(0x638f3df0,'helper_3df0')]:
  def cb(a,n=name):events.append(n);h.ret(0)
  h.callbacks[f]=cb
 rc=h.run(0x638f492c);assert rc==0 and events[:2]==['wait','clear']
 assert ('helper_3df0' in events)==(not(bits&0x10c000))
 rows.append(dict(wait_status=status,flags=hex(bits),rc=rc,calls=events))
p=Path('.local/outputs/sensor-bayer-20261030/followup');(p/'read-end-tests.json').write_text(json.dumps(dict(original_instructions=True,camera_access=False,cases=rows,limitations='Wait and downstream callbacks mocked. Does not establish event meanings or pixel DMA completion.'),indent=2));print('Passed five ReadEnd original-instruction branch tests')
