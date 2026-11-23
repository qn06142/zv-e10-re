"""Run actual ARM source allocation/range gates for full-HD buffers."""
from verify_frontend import Case,m
from unicorn.arm_const import *
from pathlib import Path
import json
class Prepare(Case):
 def __init__(self,capacity):
  self.capacity=capacity;self.requests=[];self.map_lengths=[];self.frees=0
  super().__init__();self.set('alloc_unit',self.imp('hd_alloc'));self.set('dealloc_unit',self.imp('hd_free'))
 def hook(self,u,a,n,d):
  if a in self.handlers:
   name=self.handlers[a];v=[u.reg_read(r) for r in m.R];r=None
   if name=='hd_alloc':
    assert v[1]==0x127;self.requests.append(v[1]);m.put(u,v[2],9);m.put(u,v[3],0x15b00000);m.put(u,m.word(u,u.reg_read(UC_ARM_REG_SP)),self.capacity);r=0
   elif name=='hd_free':self.frees+=1;r=0
   elif name=='open' and m.cstr(u,v[0])=='/dev/stream':r=10
   elif name=='mmap':self.map_lengths.append(v[1]);r=0x41000000
   if r is not None:u.reg_write(UC_ARM_REG_R0,r);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR));return
  super().hook(u,a,n,d)
rows=[]
for cap,expected in [(3276800,22),(4147199,22),(4147200,0),(8388608,0)]:
 c=Prepare(cap);result=c.run('ensure_source.part.0');assert result==expected and c.requests==[0x127]*(5 if expected else 1)
 assert bool(c.map_lengths)==(not expected)
 if c.map_lengths:assert c.map_lengths==[4149248]
 else:assert c.frees==5
 rows.append({'capacity':cap,'returncode':result,'mapped_bytes':c.map_lengths,'deallocations':c.frees})
Path('.local/outputs/hd-v41/source-capacity-verification.json').write_text(json.dumps({'compiled_ARM_executed':True,'hardware_calls_mocked':True,'cases':rows},indent=2));print('4 full-HD source allocation cases passed')
