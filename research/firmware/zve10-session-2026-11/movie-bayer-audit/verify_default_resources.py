"""Execute original resource initialization and default drive-mode lookup."""
import argparse,sys,json
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('repo',type=Path);a=p.parse_args()
sys.path.insert(0,str(a.repo/'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness,MEM
from rtos import word
h=Harness();h.run(0x6379bf60)
list_addr=word(0x64638120+0x4490)
resources={h.word(h.word(list_addr+4*i)+4):h.word(list_addr+4*i) for i in range(27) if h.word(list_addr+4*i)}
results=[]
for mode in range(0x95):
 resource=h.run(0x637a6d78,mode,MEM)
 if not resource:continue
 assert resource in resources
 obj=resources[resource]
 write0=h.run(0x63d22ca4,obj,0);write1=h.run(0x63d22ca4,obj,1)
 # The unmodified mode lookup never enables logical Aif 5/6.
 assert not write0 and not write1,(mode,resource)
 results.append(dict(drive_mode=hex(mode),resource=hex(resource),flags=hex(h.word(obj+0x28))))
assert len(results)==23
assert h.word(resources[0x2f]+0x28)==0x200001
assert h.run(0x63d22ca4,resources[0x2f],0)==1
print(json.dumps(dict(mocks=0,drive_modes_tested=149,nonzero_modes=len(results),raw_resource_2f_present=True,results=results),indent=2))
