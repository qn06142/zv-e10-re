"""Exercise native DFE constructors and parameter headers for every default drive mode.
Mocks cover atexit, OS locks and logging; ROM scripts and module headers execute unchanged.
"""
import argparse,sys,json
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('repo',type=Path);a=p.parse_args()
sys.path.insert(0,str(a.repo/'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness,MEM
from rtos import word,DATA,BASE
from unicorn import UC_HOOK_MEM_WRITE
h=Harness();h.u.mem_map(0xfc000000,0x400000)
for fn in [0x63ae1ba4,0x635df208,0x635df224,0x6396f8c4]:h.callbacks[fn]=lambda _:h.ret(0)
logs=[]
h.callbacks[0x6396f8c4]=lambda args:(logs.append(args),h.ret(0))
h.run(0x6379d44c);h.run(0x6379bf60);h.run(0x637a6d90)
table=word(0x64638120+0x4490)
resources={h.word(h.word(table+4*i)+4):h.word(table+4*i) for i in range(27) if h.word(table+4*i)}
results=[]
writes=[]
h.u.hook_add(UC_HOOK_MEM_WRITE,lambda u,access,address,size,value,data:writes.append((address,value)) if 0xfc000000<=address<0xfc400000 else None)
for mode in range(149):
 default=h.run(0x637a6d78,mode,MEM)
 if not default:continue
 owner=h.run(0x637a6e88,0,mode,0);runtime=h.run(0x637a6c84,mode,0)
 for resource in [default,0x2f]:
  h.u.mem_write(owner,DATA[owner-BASE:owner-BASE+0xc0])
  op=resources[resource];h.put(op,0x123456)
  # Cause the native header path to re-evaluate the drive-mode scripts.
  h.put(op+8,0xba)
  for i,v in enumerate([mode,owner,runtime,0]):h.put(MEM+4*i,v)
  status=h.run(0x6379a510,op,0x123456,MEM)
  assert status==0
  raw={hex(offset):hex(h.word(owner+offset)) for offset in [0x5c,0x60,0x6c,0x70]}
  assert all(h.word(owner+offset)==0 for offset in [0x5c,0x60]),(mode,resource,raw)
  if resource==0x2f:
   # Attempt the real RAW setup using the native header geometry, not a supplied substitute.
   h.put(MEM+0x10c,3);h.put(MEM+0x114,0x20000000);h.put(MEM+0x118,0x1800000);h.put(MEM+0x11c,2)
   writes.clear();logs.clear()
   h.run(0x6379e2b8,0x6426aea0,MEM,MEM+0x100)
   assert not writes,(mode,writes)
   assert len(logs)==1 and logs[0][0]==0x63f65cac,(mode,logs)
  results.append(dict(drive_mode=hex(mode),resource=hex(resource),owner=hex(owner),sensor_script=hex(h.word(owner+8)),raw_geometry=raw))
print(json.dumps(dict(cases=len(results),mocks=['atexit','OS locks','logger'],results=results),indent=2))
