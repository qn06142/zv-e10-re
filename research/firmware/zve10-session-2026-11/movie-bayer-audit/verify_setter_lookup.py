"""Prove setter lookup returns wrapper addresses, not frame buffers."""
import argparse,sys
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('repo',type=Path);a=p.parse_args()
sys.path.insert(0,str(a.repo/'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness,MEM
h=Harness();obj=MEM+0x1000;cases=0
for fn,offset in ((0x63d9628a,0x684),(0x63d962a8,0x6a8),(0x63d962c4,0x738)):
 for selector in (0,1,2):
  wrapper=obj+offset+12*selector
  for pointer in (0,0x12345678,0x20000000):
   h.put(wrapper+4,pointer)
   assert h.run(fn,obj,selector)==(wrapper if pointer else 0)
   cases+=1
print(f'{cases} original-instruction cases, zero mocks: returns wrapper iff wrapper+4 is nonzero')
