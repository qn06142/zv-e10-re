"""Execute original native consumer resolution policy against saved metadata; no camera access."""
from pathlib import Path
import sys,json,struct,hashlib
sys.path.insert(0,'.local/work/yc-frame-contract-20261029')
from rtos_harness import *

def run_case(name,raw,expect_image,expect_pixel):
 h=Harness();u=h.u
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
 image=MEM+0x4000;u.mem_write(image,bytes(60))
 image_rc=h.run(0x63c60f76,YC,image)
 assert image_rc==expect_image,(name,image_rc)
 baseline=len(transactions)
 result={}
 for label,pc in [('open_pixels',0x63691ebc),('share_pixels',0x63691f94),('close_pixels',0x63692218)]:
  begin=len(transactions);rc=h.run(pc,THIS,YC)
  result[label]=dict(rc=rc,dmm=transactions[begin:])
 h.callbacks[0x6364db3c]=lambda a:h.ret(MEM+0x9000)
 h.callbacks[0x63c60b98]=lambda a:h.ret(1)
 begin=len(transactions);rc=h.run(0x63c868c0,THIS,YC,0,0,2)
 result['free_pixels']=dict(rc=rc,dmm=transactions[begin:])
 pix=transactions[baseline:]
 assert [(x['opcode'],x['handle']) for x in pix]==([(5,'0x7f24'),(2,'0x7f24'),(6,'0x7f24'),(4,'0x7f24')] if expect_pixel else []),(name,pix)
 begin=len(transactions)
 assert h.run(0x63692180,THIS,MSG)==0
 assert h.run(0x63c867f0,THIS,YC,2)==0
 meta_ops=transactions[begin:]
 assert [(x['opcode'],x['handle']) for x in meta_ops]==[(6,'0x8cc9'),(4,'0x8cc9')],(name,meta_ops)
 return dict(case=name,raw_sha256=hashlib.sha256(raw).hexdigest(),original_getter_return=image_rc,image_wire=bytes(u.mem_read(image,60)).hex(),pixel_operations=result,metadata_cleanup=meta_ops)

real=Path('.local/outputs/vga-v39/capture-first-01/logs/rejected-source.yc38').read_bytes()[80:4176]
ref=Path('.local/outputs/vga-v33/capture-first-01/logs/source-ssyc-retained.bin').read_bytes()
a=bytearray(ref);a[64]=0
b=bytearray(ref);b[72:74]=bytes(2)
bad=Path('.local/outputs/vga-v38/capture-first-01/logs/rejected-source.yc38').read_bytes()[80:4176]
rows=[run_case('actual_v39_attach0_type2_handle0',real,1,False),run_case('reference_attached_image',ref,1,True),run_case('control_attach0_nonzero_handle',bytes(a),1,False),run_case('control_attach1_zero_handle',bytes(b),1,False),run_case('actual_v38_malformed',bad,0,False)]
out=dict(camera_access=False,original_Sony_code_executed=True,cases=rows,limitations=['DMM transport, physical mapping and cache-release lookup are mocked.','Individual helpers are invoked by the harness; no entire asynchronous lifecycle is executed.','No-image gating is proved for these helpers; SEND reference ownership and safe event completion still need separate proof.'])
Path('.local/outputs/yc-resolution-audit-20261030/native-image-presence.json').write_text(json.dumps(out,indent=2))
for r in rows:print(r['case'],r['original_getter_return'],{k:len(v['dmm']) for k,v in r['pixel_operations'].items()})
