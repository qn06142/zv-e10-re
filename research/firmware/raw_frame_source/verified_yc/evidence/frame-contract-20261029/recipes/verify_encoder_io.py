from pathlib import Path
import json,struct,hashlib
from rtos_harness import *
h=Harness();u=h.u
raw=Path('.local/outputs/vga-v33/capture-first-01/logs/source-ssyc-retained.bin').read_bytes();assert hashlib.sha256(raw).hexdigest()=='9c60c7088da03631af4cd06fbd8f9d444d084e9104ead87cb0147ef76ac45f9c'
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
assert h.run(0x63691ebc,THIS,YC)==0
image=MEM+0x4000;assert h.run(0x63c60f76,YC,image)==1
native=bytes(u.mem_read(image,60));assert struct.unpack_from('<H',native,8)[0]==0x7f24
assert h.run(0x63691f94,THIS,YC)==0
assert h.run(0x63692038,THIS,YC)==0
assert h.run(0x63692218,THIS,YC)==0
assert h.run(0x63692180,THIS,MSG)==0
# Choose the real helpers' non-cached path; cache lookup is a mocked environment condition.
h.callbacks[0x6364db3c]=lambda a:h.ret(MEM+0x9000)
h.callbacks[0x63c60b98]=lambda a:h.ret(1)
assert h.run(0x63c868c0,THIS,YC,0,0,2)==0
assert h.run(0x63c867f0,THIS,YC,2)==0
assert [(x['opcode'],x['handle']) for x in transactions]==[(5,'0x8cc9'),(5,'0x7f24'),(2,'0x7f24'),(2,'0x8cc9'),(6,'0x7f24'),(6,'0x8cc9'),(4,'0x7f24'),(4,'0x8cc9')]
out=dict(camera_access=False,original_encoder_helpers_and_metadata_parser_executed=True,dmm_transport_mocked=True,capture_sha256=hashlib.sha256(raw).hexdigest(),functions=['open_pin_data 0x63691dec','open_image_data 0x63691ebc','share_image_data 0x63691f94','share_pin_data 0x63692038','close_image_data 0x63692218','close_pin_data 0x63692180','release image 0x63c868c0 -> 0x63c86868 -> 0x63c60c64','release pin 0x63c867f0 -> 0x63c60c64'],native_image_info_hex=native.hex(),transactions=transactions,limitations=['Handles and addresses are controlled fixture bindings for the real saved descriptor.','Original helpers and parser execute; DMM state changes and hardware access are mocked.','Opening a unit is distinct from sharing or freeing it.','DMM transport and the non-cached release lookup are mocked; reference counts are not live measurements.'])
Path('.local/outputs/yc-frame-contract-20261029/encoder-original-io.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
