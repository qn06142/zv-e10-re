from pathlib import Path
import json,struct
from rtos_harness import *
raw=bytes.fromhex('0020030044000000070034123412341234123412000000000403020134120000000000000001000000000000000000000000000000000000443322117856000000000000')
source=bytes.fromhex('0100000095020000247f0000000000000200000080073804800738040000000080073804000000008007380400000201010102014000000067000000')
dest=bytearray(source);struct.pack_into('<H',dest,8,0x2345)
for off in [0x14,0x18,0x20,0x28]:struct.pack_into('<HH',dest,off,640,480)
dest[0x2f]=0;dest[0x30]=0;dest[0x31]=0
cases=[]
for poison in [0,0xa5]:
 h=Harness();u=h.u;obj=MEM;packet=MEM+0x1000
 assert h.run(0x636c6420,obj)==obj
 inner=bytearray(232);struct.pack_into('<HHHH',inner,0,0x2000,3,232,0);inner[28:28+68]=raw;inner[96:]=bytes([poison])*136;u.mem_write(packet,bytes(inner))
 def image(a):
  handle=struct.unpack('<H',u.mem_read(a[1]+4,2))[0];u.mem_write(a[2],source if handle==0x1234 else bytes(dest));h.ret(0)
 h.callbacks[0x63ca47b8]=image
 h.callbacks[0x636ba508]=lambda a:(u.mem_write(a[2],bytes(8)),h.ret(0))
 h.callbacks[0x636ba8e4]=lambda a:(u.mem_write(a[2],bytes(20)),h.ret(0))
 h.callbacks[0x63ca326a]=lambda a:h.ret(MEM+0x20000 if h.word(a[1])==0x295 else MEM+0x30000)
 h.callbacks[0x63cadcfe]=lambda a:h.ret(0)
 h.callbacks[0x636badb8]=lambda a:h.ret(0)
 h.callbacks[0x636bad44]=lambda a:h.ret(0)
 h.callbacks[0x63c5fe48]=lambda a:h.ret(0)
 rc=h.run(0x63cade3a,obj,packet);assert rc==0,hex(rc)
 state=bytes(u.mem_read(obj,0x29c));cases.append(dict(poison=poison,rc=rc,state_hex=state.hex()))
a=bytes.fromhex(cases[0]['state_hex']);b=bytes.fromhex(cases[1]['state_hex']);diff=[hex(i) for i,(x,y) in enumerate(zip(a,b)) if x!=y]
out=dict(camera_access=False,original_api_constructor_and_command_parser_executed=True,functions=['ApiResizeRotate constructor0x636c6420','command parser0x63cade3a'],mocked=['source/destination metadata resolution and capacity response','YC state and auxiliary metadata reads','physical mapping','diagnostic logging'],tail_bytes_compared=[0,165],object_different_offsets=diff,cases=cases,limitations=['Metadata/capacity are fixture results, not live DMM or hardware acceptance.','This tests default command version0 only; version1/2 require their extended fields.'])
Path('.local/outputs/yc-frame-contract-20261029/sdf-short-command-parse.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='cases'},indent=2))
