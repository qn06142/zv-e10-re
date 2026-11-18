"""Execute full DFECore::CamAif setup with native format/geometry calculations.
Firmware object fields are fixtures; MMIO is RAM, not a timing model.
"""
import argparse,sys,struct,json
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('repo',type=Path);a=p.parse_args()
sys.path.insert(0,str(a.repo/'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness,MEM
h=Harness();obj=MEM+0x1000;dma=MEM+0x2000;request=MEM+0x3000;owner=MEM+0x4000;geom=MEM+0x5000;param=MEM+0x6000
encoder=MEM+0x7000
base=0xfc0a9000
h.u.mem_map(0xfc000000,0x100000)
h.run(0x637a36ec,encoder,0)
h.run(0x637a3be0,dma,3,0)
h.run(0x6379e248,obj,5,dma,encoder)
h.put(request+4,owner);h.put(owner+0x5c,geom)
h.u.mem_write(geom,struct.pack('<6H',1920,0,0,1920,1080,0))
logs=[]
h.callbacks[0x6396f8c4]=lambda args:(logs.append(dict(args=args,dma_address=hex(h.word(base+0x220)))),h.ret(0))
results=[]
for fmt,row_bytes in ((0,3840),(3,2880)):
 for repeat in (1,2,3):
  for capacity in (1024,row_bytes*1080,row_bytes*1080*repeat):
   h.u.mem_write(base,bytes(4096));h.u.mem_write(0xfc0a8000,bytes(4096));logs.clear()
   for offset,value in ((0xc,fmt),(0x10,0),(0x14,0x20000000),(0x18,capacity),(0x1c,repeat)):h.put(param+offset,value)
   h.run(0x6379e2b8,obj,request,param)
   regs=[h.word(base+0x200+offset) for offset in range(0x20,0x48,4)]
   assert regs[0]==0x20000000 and regs[1]==row_bytes,(fmt,repeat,regs)
   assert regs[2]==0 and regs[3]==1079,(fmt,repeat,regs)
   assert (h.word(0xfc0a8014)&3)==(3 if fmt==3 else 0)
   if fmt==3:assert h.word(0xfc0a8910)==((119<<16)|1079)
   assert regs[5]==(repeat-1 if repeat>1 else 0)
   assert len(logs)==int(capacity<row_bytes*1080),(fmt,repeat,capacity,logs)
   results.append(dict(format=fmt,repeat=repeat,capacity=capacity,registers=[hex(v) for v in regs],undersize_logged=bool(logs)))
print(json.dumps(dict(cases=len(results),mocked=['logger only'],results=results),indent=2))
