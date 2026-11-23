from pathlib import Path
import struct,json
from rtos_harness import *
h=Harness();u=h.u;share=[];sends=[]
h.callbacks[0x63c48e0c]=lambda a:h.ret(a[0])
assert h.run(0x63744f2c)==0
# These pointers are resolved by the original VDF initializer's GOT references.
got=0x63744f46+4+fw_word(0x63744f90);pins=h.word(got+fw_word(0x63744f98));pin=pins+2*56
assert list(struct.unpack('<4I',u.mem_read(pin+24,16)))==[0,2,0,0x0059000e]
# Isolated controlled connected-state fixture, not a live connection.
u.mem_write(pin+8,struct.pack('<4I',0,1,0,0x00570050));h.put(pin+0x28,0)
owner=MEM+0x8000;h.put(owner,0x645852c8)
h.callbacks[0x637489d4]=lambda a:h.ret(owner)
def share_packet(a):
 share.append(dict(type=hex(h.word(a[0])),handle=hex(struct.unpack('<H',u.mem_read(a[0]+4,2))[0]),mode=a[1]));u.mem_write(a[2],b'\0\0');h.ret(0)
h.callbacks[0x6371f60c]=share_packet
h.callbacks[0x63740f30]=lambda a:h.ret(MEM+0x9000)
h.callbacks[0x637137c8]=lambda a:h.ret(MEM+0x9000)
h.callbacks[0x63ce2676]=lambda a:h.ret(0)
def send(a):
 msg=a[2];p=msg+0x24;n=struct.unpack('<H',u.mem_read(p+4,2))[0];assert n==52,(hex(msg),n,bytes(u.mem_read(msg,96)).hex())
 b=bytes(u.mem_read(p,n));sends.append(dict(destination=hex(a[1]),packet_hex=b.hex(),source_properties=list(struct.unpack_from('<4I',b,8)),destination_properties=list(struct.unpack_from('<4I',b,24)),type=hex(struct.unpack_from('<I',b,40)[0]),sds=hex(struct.unpack_from('<H',b,44)[0]),offset=struct.unpack_from('<I',b,48)[0]));h.ret(0)
h.callbacks[0x63ac26a0]=send
h.callbacks[0x6374c5e8]=lambda a:u.reg_write(UC_ARM_REG_PC,STOP)
h.put(MEM+0x6000,MEM+0x7000);h.put(MEM+0x7000+0xb4,0x63cf57a1)
h.put(MEM+0x5000,MEM+0xa000);h.put(MEM+0xa000+0x118,STOP+0x100|1);h.put(MEM+0xb000,0)
h.callbacks[STOP+0x100]=lambda a:h.ret(MEM+0xb000)
raw=Path('.local/outputs/vga-v33/capture-first-01/logs/source-ssyc-retained.bin').read_bytes();u.mem_write(MEM+0x10000,raw);h.put(STACK+0x350,MEM+0x10000)
u.mem_write(MEM+0x4000,bytes.fromhex('0100000095020000247f0000000000000200000080073804800738040000000080073804000000008007380400000201010102014000000067000000'))
h.put(STACK+0x344,0xe0b00);u.mem_write(STACK+0x348,struct.pack('<H',0x8cc9))
u.reg_write(UC_ARM_REG_R4,MEM+0x5000);u.reg_write(UC_ARM_REG_R5,MEM+0x6000);u.reg_write(UC_ARM_REG_R7,MEM+0x4000)
h.run(0x6374c500)
assert share==[dict(type='0x295',handle='0x7f24',mode=0)]
assert len(sends)==1 and sends[0]['type']=='0xe0b00' and sends[0]['sds']=='0x8cc9'
out=dict(camera_access=False,original_producer_block_and_pin_serialization_executed=True,entry='0x6374c500',stop='0x6374c5e8',pin_array_base=hex(pins),selected_pin_array_index=2,shares=share,sends=sends,mocked=['identity physical mapping','producer mode getter returns mode0 (multi-segment branch skipped)','ownership manager factory','pixel DMM Share transport/helper','log availability','OSAL SendASync'],limitations=['Connected state and peer are controlled fixtures; no connection requested on camera.','Proves this producer places SDS at+0x2c and pixel Share precedes Send, not that arbitrary pool metadata is fresh.','Does not establish metadata allocation transfer or producer completion timing; those are separate stages.'])
# Resolve Category2 through the original VDF parser and inspect its send-time mutation.
assert h.run(0x63712f58,MEM+0xc000,MEM+0x10000)==MEM+0xc000
cat2=h.run(0x63ce259a,MEM+0xc000,2);assert h.word(cat2+8)==0xffffffff
out['category2_transfer_word_at_send']='0xffffffff'
out['category2_original_transfer_word']='0x197c'
Path('.local/outputs/yc-frame-contract-20261029/producer-share-send-original.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
