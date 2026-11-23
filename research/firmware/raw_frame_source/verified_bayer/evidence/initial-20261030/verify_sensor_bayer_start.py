from pathlib import Path
import sys,json,struct
sys.path.insert(0,str(Path('.local/work/yc-frame-contract-20261029').resolve()))
from rtos_harness import *
h=Harness();P=MEM+0x1000;C=MEM+0x2000;S=MEM+0x3000;mail=MEM+0x4000;result=MEM+0x4100;events=[]
for f in [0x63d20228,0x63d20248,0x63df15da,0x6396f8c4]:h.callbacks[f]=lambda a:h.ret(0)
h.callbacks[0x63d20260]=lambda a:h.ret(7)
def info(a):h.put(a[2]+16,S);h.ret(0)
h.callbacks[0x63df168e]=info;h.callbacks[0x63c48e0c]=lambda a:h.ret(S)
for i,o in enumerate([2,0x18,0x1a,0x30,0x40]):h.u.mem_write(P+o,struct.pack('<H',0x100+i))
h.u.mem_write(P+0x42,b'\xff\xff')
for o,v in [(0x20,1920),(0x24,1920),(0x32,1920),(0x34,1080)]:h.u.mem_write(P+o,struct.pack('<H',v))
for o,v in [(4,0),(8,0x3000),(0xc,0x3800),(0x10,0x4400),(0x14,0x4800),(0x1c,0)]:h.put(P+o,v)
def mapunit(a):events.append(dict(handle=a[1]));h.ret(0x20000000+a[1]*0x10000)
h.callbacks[0x63b31b14]=mapunit
h.callbacks[0x63df19ea]=lambda a:h.ret(0)
def before_submit(a):events.append(dict(stop='before shared hardware submission',state_hex=bytes(h.u.mem_read(S,0x88)).hex()));h.u.reg_write(UC_ARM_REG_PC,STOP)
h.callbacks[0x63dd3548]=before_submit
h.put(STACK,result)
# Harness.run sets argument stack itself only when more than four args supplied.
h.run(0x63b324d4,3,0x1234,P,mail,result,balanced=False)
assert events[-1].get('stop') and [x['handle'] for x in events[:-1]]==[0x102,0x100,0x101,0x103,0x104],events
out=dict(original_instructions=True,entry='0x63b324d4',stopped_before_hardware=True,events=events,limitations=['Handle resolution/resource lookup mocked. Field dimensions are chosen fixture values; neither accepted sensor mode nor Bayer packing is proven.'])
Path('.local/outputs/sensor-bayer-20261030/start-parameter-tests.json').write_text(json.dumps(out,indent=2));print('Original start validator reaches submission with five resolved buffer handles; no hardware executed')
