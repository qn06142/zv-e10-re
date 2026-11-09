"""Native DFE interrupt callback aggregation; injected status, no DMA or pixels."""
import argparse,sys,json
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('repo',type=Path);a=p.parse_args()
sys.path.insert(0,str(a.repo/'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness,MEM
from unicorn.arm_const import UC_ARM_REG_R1
h=Harness();h.u.mem_map(0xfc000000,0x100000)
callbacks=0
callback=MEM+0x2000

def complete(_):
 global callbacks
 callbacks+=1;h.ret(0)
h.callbacks.update({callback:complete,0x635df208:lambda _:h.ret(0),0x635df224:lambda _:h.ret(0),0x6396f8c4:lambda _:h.ret(0)})
slot=0x64138388;accumulator=0x64138400
results=[]
for selector in range(1,256):
 # Native selector conversion is also used by callback registration.
 low=h.run(0x63d23916,selector);high=h.u.reg_read(UC_ARM_REG_R1)
 h.u.mem_write(slot,bytes(0x48));h.u.mem_write(accumulator,bytes(8))
 h.put(slot,low);h.put(slot+4,high);h.put(slot+8,callback|1)
 # A first partial arrival must wait for the rest of the requested mask.
 bits=[(1<<i,0) for i in range(32) if low&(1<<i)]+[(0,1<<i) for i in range(32) if high&(1<<i)]
 start=callbacks
 for i,(lo,hi) in enumerate(bits):
  h.put(0xfc0a0014,lo);h.put(0xfc0a002c,hi)
  h.run(0x6379ef08)
  assert callbacks-start==int(i==len(bits)-1),(selector,i,callbacks-start)
 assert h.word(slot+8)==0
 # One-shot registration must not emit another completion on duplicate status.
 h.put(0xfc0a0014,low);h.put(0xfc0a002c,high);h.run(0x6379ef08)
 assert callbacks-start==1
 results.append(dict(selector=selector,status_low=hex(low),status_high=hex(high),arrivals=len(bits)))
# Identify which operation flags are even included in this native completion.
flags=[]
for bit in range(32):
 h.put(MEM+0x28,1<<bit)
 sel=h.run(0x63d22d02,MEM)
 if sel:flags.append(dict(operation_flag_bit=bit,selector=hex(sel)))
print(json.dumps(dict(cases=len(results),callback_count=callbacks,operation_flags=flags,results=results),indent=2))
