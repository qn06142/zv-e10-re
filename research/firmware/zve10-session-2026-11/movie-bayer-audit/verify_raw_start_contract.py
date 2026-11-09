"""Run native CamAif/RAW Aif start gates with explicitly unconfigured RAM MMIO.

This demonstrates local caller preconditions, not a physical DMA start or frame.
"""
import argparse,json,sys,itertools
from pathlib import Path
from unicorn import UC_HOOK_MEM_WRITE
p=argparse.ArgumentParser(description=__doc__);p.add_argument('repo',type=Path);a=p.parse_args()
sys.path.insert(0,str(a.repo/'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness,MEM
h=Harness();h.u.mem_map(0xfc000000,0x100000)
formatter,dma,obj=MEM,MEM+0x100,MEM+0x200
h.run(0x637a36ec,formatter,0);h.run(0x637a3be0,dma,3,0)
h.run(0x6379e248,obj,5,dma,formatter)
writes=[];logs=[]
h.u.hook_add(UC_HOOK_MEM_WRITE,lambda u,access,addr,size,value,data:writes.append((hex(addr),hex(value))),begin=0xfc000000,end=0xfc0fffff)
h.callbacks[0x6396f8c4]=lambda args:(logs.append(args),h.ret(0))
h.run(0x63d2345a,obj)
initialization_writes=list(writes)
assert initialization_writes==[
    ('0xfc0a0000','0x80'),('0xfc0a0000','0x8000'),
    ('0xfc0a9000','0x4'),('0xfc0a9000','0x2'),('0xfc0a8700','0x100')]
rows=[]
for module_enabled,requested,skip,enabled,busy,error in itertools.product([0,1],repeat=6):
    h.u.mem_write(0xfc0a8000,bytes(0x2000))
    h.u.mem_write(obj+0x14,bytes([module_enabled]));h.u.mem_write(dma+9,bytes([skip]))
    h.put(0xfc0a9200,enabled);h.put(0xfc0a9204,requested|(busy<<31));h.put(0xfc0a9208,error)
    writes.clear();logs.clear()
    h.run(0x63d23398,obj)
    should_write=module_enabled and not requested and not skip
    assert h.word(0xfc0a9200)==(1 if should_write else enabled)
    assert h.word(0xfc0a9220)==0 and h.word(0xfc0a9224)==0
    assert bool(writes)==bool(should_write)
    assert len(logs)==int(bool(should_write and not enabled and not busy and error))
    rows.append(dict(module_enabled=module_enabled,requested=requested,skip=skip,
                     prior_enabled=enabled,busy=busy,error_low5=error,
                     post_enabled=h.word(0xfc0a9200),destination=hex(h.word(0xfc0a9220)),
                     line_bytes=h.word(0xfc0a9224),writes=list(writes),log_count=len(logs)))
assert len(rows)==64
print(json.dumps(dict(cases=len(rows),native_cam_aif_start='0x63d23398',
    native_cam_aif_initialize='0x63d2345a',initialization_writes=initialization_writes,
    native_aif_start='0x637a3ad0',mocked=['logger','harness memory helpers'],
    fixture='constructed objects with deliberately unconfigured RAM-backed destination/line registers',
    dma_executed=False,pixels_emulated=False,
    finding='start gating checks state but does not locally validate a configured destination or line length',rows=rows),indent=2))
