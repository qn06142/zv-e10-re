"""Adversarial native CamAif stop polling: bounded return is not idle proof.

Busy/status registers are fixtures. No timing, DMA, bus flush or pixel model.
"""
import argparse,json,sys
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('repo',type=Path)
a=p.parse_args()
sys.path.insert(0,str(a.repo/'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness,MEM

h=Harness();h.u.mem_map(0xfc000000,0x100000)
obj=MEM+0x1000;base=0xfc0a9000
h.run(0x637a3be0,obj,3,0)
assert h.word(obj+4)==base
logs=[]
h.callbacks[0x6396f8c4]=lambda args:(logs.append(args),h.ret(0))
polls=0;active=False;clear_after=0
def busy_register(args):
    global polls
    if active:
        busy=clear_after is None or polls<clear_after
        h.put(base+0x204,(h.word(base+0x204)&0x7fffffff)|(int(busy)<<31))
        polls+=1
    # Observe and supply RAM register fixture, then execute original getter.
h.callbacks[0x63d26260]=busy_register
rows=[]
for clear_after in [0,1,2,998,999,1000,1001,None]:
    for status_low5 in [0,1,31]:
        h.u.mem_write(base,bytes(4096))
        h.put(base+0x204,0x80000001)
        h.put(base+0x208,status_low5)
        h.put(base+0x210,0x12345678)
        polls=0;logs.clear();active=True
        result=h.run(0x637a3c48,obj)
        active=False
        busy=h.run(0x63d2626e,obj)
        assert polls==min((clear_after+1 if clear_after is not None else 1000),1000)
        assert busy==int(clear_after is None or clear_after>=1000)
        assert h.word(obj+0xc)==0x12345678
        assert result==0x12345678  # Last register snapshot, not an idle/error result.
        assert (h.word(base+0x208)>>31)==int(bool(status_low5))
        rows.append(dict(clear_after_busy_observations=clear_after,status_low5=status_low5,
                         polls=polls,logs=len(logs),returned=hex(result),busy_after_return=busy,
                         control=hex(h.word(base+0x204)),status=hex(h.word(base+0x208))))
print(json.dumps(dict(cases=len(rows),native_stop='0x637a3c48',native_busy_getter='0x63d2626e',
    native_raw_busy_read='0x63d26260',mocked_boundaries=['logger','harness memory helpers'],
    register_fixtures=['busy observation sequence','status bits','snapshot word'],
    finding='Native stop returns after 1000 busy observations even if busy remains asserted; return value is a register snapshot.',
    dma_or_timing_emulated=False,rows=rows),indent=2))
