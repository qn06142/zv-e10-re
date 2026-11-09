"""Check original RTOS DMA address programming against the firmware's channel table.
MMIO is RAM-backed: this verifies instructions/register values, never hardware completion.
"""
import argparse,sys,struct,json
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('repo',type=Path);args=p.parse_args()
sys.path.insert(0,str(args.repo/'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness,MEM
from rtos import word
h=Harness()
# Include the readback fence pointed to by GOT+0x8880.
fence=word(0x64638120+0x8880)
regions={fence&~4095}
channels=(0,1,3,4,6,10,17,18,22)
table=word(0x64638120+0x9120)
for channel in channels:
    regions.add(word(table+12*channel+4)&~4095)
for region in sorted(regions):
    if not any(begin <= region <= end for begin,end,_ in h.u.mem_regions()):h.u.mem_map(region,4096)
param=MEM+0x1000
cases=[]
for channel in channels:
    base=word(table+channel*12+4)
    for address in (0x20000000,0x23456000,0x30000000,0xfffffff0):
        h.u.mem_write(base,bytes(0x80))
        h.u.mem_write(param,struct.pack('<4H4I',1079,0,0,0,address,3840,0,0))
        h.run(0x639e2140,channel,param)
        actual=[h.word(base+o) for o in range(0x28,0x48,4)]
        assert actual==[address,1079,3840,0,0,0,0,0],(channel,actual)
        # Only configuration: this routine does not set the start bit.
        assert h.word(base)&1==0
        cases.append(dict(channel=channel,register_base=hex(base),address=hex(address)))
print(json.dumps(dict(cases=len(cases),mocks=0,fence=hex(fence),results=cases),indent=2))
