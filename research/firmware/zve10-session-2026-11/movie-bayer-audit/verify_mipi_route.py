"""Trace active Ofmt_Mwrap into native MIPI Tx ownership and packet type setup.
This verifies the software route, not a receiver buffer or live cadence.
"""
import argparse,sys,json
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('repo',type=Path);a=p.parse_args()
sys.path.insert(0,str(a.repo/'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness,MEM
from rtos import word,DATA,BASE,cstr
h=Harness();h.u.mem_map(0xfc000000,0x400000)
for fn in [0x63ae1ba4,0x635df208,0x635df224,0x6396f8c4]:h.callbacks[fn]=lambda _:h.ret(0)
h.run(0x6379d44c);h.run(0x6379bf60);h.run(0x637a6d90)
modules=word(0x64638120+0x7c0)
# RTTI is read from the actual native-constructed objects.
def typename(obj):
 v=h.word(obj);return cstr(h.word(h.word(v-4)+4))
assert typename(0x6426ac50)=='N6Camera7DFECore6MipiTxE'
assert typename(h.word(0x6426ac50+0xc))=='N6Camera7DFECore14MipiCsi2TxCtrlE'
assert typename(h.word(0x6426ac50+0x10))=='N6Camera7DFECore15MipiDphyTxMacroE'
resources={}
table=word(0x64638120+0x4490)
for i in range(27):
 obj=h.word(table+4*i)
 if obj:resources[h.word(obj+4)]=obj
acquires=[]
h.callbacks[0x637a1e04]=lambda args:(acquires.append(args[:2]),h.ret(1))
# Native per-data-type bit-length function; invalid types explicitly log and fall back14.
decode_obj=MEM+0x4000;decode_regs=MEM+0x5000;h.put(decode_obj+4,decode_regs)
expected={0x2b:10,0x2c:12,0x2d:14,0x30:4,0x31:8}
for dt,bits in expected.items():
 h.put(decode_regs+0x84,dt);assert h.run(0x637a277c,decode_obj)==bits
results=[]
for mode in range(149):
 rid=h.run(0x637a6d78,mode,MEM)
 if not rid:continue
 op=resources[rid];h.put(op,123);h.put(op+8,0xba)
 owner=h.run(0x637a6e88,0,mode,0);runtime=h.run(0x637a6c84,mode,0)
 h.u.mem_write(owner,DATA[owner-BASE:owner-BASE+0xc0])
 h.u.mem_write(0xfc0a7000,bytes(4096))
 for i,v in enumerate([mode,owner,runtime,0]):h.put(MEM+4*i,v)
 assert h.run(0x6379a510,op,123,MEM)==0
 dtype=h.word(0xfc0a7064)&0x3f
 acquires.clear()
 h.run(0x637a24d4,0x6426acc0)
 assert acquires==[[0x6426ac50,0]],(mode,acquires)
 assert h.word(0xfc0a7000)==1
 results.append(dict(drive_mode=hex(mode),resource=hex(rid),vc0_data_type=hex(dtype),native_bit_length=expected.get(dtype),vc0_packet_word_count=h.word(0xfc0a7068)&0xffff,mipi_tx_object=hex(acquires[0][0])))
print(json.dumps(dict(cases=len(results),mocks=['atexit','OS locks','logger','MIPI acquire hardware boundary'],data_type_decoder={hex(k):v for k,v in expected.items()},results=results),indent=2))
