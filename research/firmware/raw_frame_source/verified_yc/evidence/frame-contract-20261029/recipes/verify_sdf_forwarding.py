from pathlib import Path
import json,struct
from rtos_harness import *
h=Harness();u=h.u;captured=[]
raw=bytes.fromhex('0020030044000000070034123412341234123412000000000403020134120000000000000001000000000000000000000000000000000000443322117856000000000000')
assert len(raw)==68
obj=MEM;command=MEM+0x1000;context=MEM+0x2000;resource=MEM+0x3000
h.put(obj+8,0x56000f);u.mem_write(command,raw+bytes([0xa5])*(256-len(raw)))
u.mem_write(context,struct.pack('<IIHHHHHHH2x',0x80003b,0x80003b,0x2000,3,0,0,0,0,0));u.mem_write(resource,struct.pack('<II',MEM+0x5000,0))
h.callbacks[0x63c5fe48]=lambda a:h.ret(0)
def send(a):
 p=a[2]+0x24;n=struct.unpack('<H',u.mem_read(p+4,2))[0];b=bytes(u.mem_read(p,n));captured.append(dict(destination=hex(a[1]),bytes=n,payload_hex=b.hex()));h.ret(0)
h.callbacks[0x63ac26a0]=send
assert h.run(0x636bdf10,obj,command,context,resource,0)==0
b=bytes.fromhex(captured[0]['payload_hex']);assert len(b)==232 and b[28:28+68]==raw
out=dict(camera_access=False,original_sdf_forwarder_executed=True,forwarder='0x636bdf10',source_sdk_bytes=68,internal_bytes=232,raw_command_embedded_at=28,source_ref_wire_offset=24,source_ref_internal_offset=52,destination_ref_wire_offset=56,destination_ref_internal_offset=84,captured=captured,tail_poison_fixture=True,limitations=['This fixture proves the 28-byte envelope insertion, not a complete hardware resize.','Forwarder copies 204 bytes from the command staging area regardless of original command length. Poison bytes make bytes beyond the 68-byte input visible.','Need trace destination override masks and tail initialization/length handling before using the expanded request as a complete ABI.'])
Path('.local/outputs/yc-frame-contract-20261029/sdf-forwarding-original.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='captured'},indent=2))
