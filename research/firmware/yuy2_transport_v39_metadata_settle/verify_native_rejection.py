import sys
sys.path.insert(0,".local/work/yc-frame-contract-20261029")
from pathlib import Path
import json,struct,hashlib
from rtos_harness import *
h=Harness();u=h.u
record=Path('.local/outputs/vga-v38/capture-first-01/logs/rejected-source.yc38').read_bytes()
raw=record[80:4176]
u.mem_write(MEM+0x10000,raw)
THIS=MEM;CTX=MEM+0x1000;MSG=MEM+0x2000;YC=MEM+0x3000
h.put(THIS,CTX);h.put(CTX,CTX+0x100);h.put(CTX+0x108,0x00570050)
packet=bytearray(52);struct.pack_into('<HHHH',packet,0,0x1000,0x102,52,1);struct.pack_into('<IHI',packet,40,0xe0b00,0x8cc9,0) # overwritten below to keep ABI padding
struct.pack_into('<I',packet,40,0xe0b00);struct.pack_into('<H',packet,44,0x8cc9);struct.pack_into('<I',packet,48,0)
u.mem_write(MSG,bytes(packet));transactions=[]
def dmm(a):
 request=bytes(u.mem_read(a[0],112));op,handle=struct.unpack_from('<HH',request,0)
 transactions.append(dict(opcode=op,handle=hex(handle),type_or_share_argument=hex(struct.unpack_from('<I',request,4)[0]),mode=struct.unpack_from('<H',request,22)[0],route=hex(a[2]),raw_hex=request.hex()))
 reply=bytearray(112);struct.pack_into('<H',reply,6,0x1111)
 if op==5:
  struct.pack_into('<H',reply,8,1);struct.pack_into('<II',reply,16,MEM+0x10000 if handle==0x8cc9 else MEM+0x20000,4096 if handle==0x8cc9 else 2073600)
 u.mem_write(a[1],bytes(reply));h.ret(0)
h.callbacks[0x6364dac0]=dmm
h.callbacks[0x63c48e0c]=lambda a:h.ret(a[0])
assert h.run(0x63645310,YC)==YC
assert h.run(0x63691dec,THIS,MSG,YC)==0

rows=[]
for name,b,expected in [('v38_first',record[80:4176],0),('v38_second',record[4176:],0),('v33_reference',Path('.local/outputs/vga-v33/capture-first-01/logs/source-ssyc-retained.bin').read_bytes(),1)]:
 u.mem_write(MEM+0x10000,b)
 u.mem_write(MEM+0x4000,bytes(60))
 rc=h.run(0x63c60f76,YC,MEM+0x4000)
 assert rc==expected,(name,rc)
 rows.append(dict(snapshot=name,sha256=hashlib.sha256(b).hexdigest(),native_image_lookup_return=rc,image_hex=bytes(u.mem_read(MEM+0x4000,60)).hex()))
out=dict(original_RTOS_getter='0x63c60f76',camera_access=False,physical_mapping_and_DMM_transport_mocked=True,cases=rows,conclusion='Both V38 snapshots are rejected by original Sony getter; V33 reference is accepted. This does not establish the cause of malformed metadata.')
Path('.local/outputs/vga-v39/native-replay-verification.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
