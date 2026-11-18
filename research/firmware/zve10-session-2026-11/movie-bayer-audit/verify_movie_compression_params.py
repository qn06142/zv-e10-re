import sys,json,struct,argparse
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('repo',type=Path);a=p.parse_args()
sys.path.insert(0,str(a.repo/'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos import word,DATA,BASE
from rtos_harness import Harness,MEM
from unicorn.arm_const import *
h=Harness();h.u.mem_map(0xfc000000,0x400000);h.u.reg_write(UC_ARM_REG_C1_C0_2,0xf00000);h.u.reg_write(UC_ARM_REG_FPEXC,0x40000000)
for fn in [0x63ae1ba4,0x635df208,0x635df224,0x6396f8c4]:h.callbacks[fn]=lambda _:h.ret(0)
h.run(0x6379d44c);h.run(0x6379bf60);h.run(0x637a6d90)
table=word(0x64638120+0x4490);op=next(h.word(table+4*i) for i in range(27) if h.word(h.word(table+4*i)+4)==0x39)
h.callbacks[0x6379be60]=lambda _:h.ret(op)
h.run(0x63d26a42,word(0x64638120+0x49e4),72,0,0,1)
records=[]
def final(args):
 records.append(dict(args=args,param=bytes(h.u.mem_read(args[2],0x28)).hex(),mode_byte=h.u.mem_read(args[2]+8,1)[0],compression_strategy=h.word(args[2]+0x10),rdc_enc_type=h.word(args[2]+12)))
 h.ret(0)
h.callbacks[0x6379a57c]=final
# Intercept the final parameter boundary. Original wrapper returns normally;
# this verifies its construction, not all downstream module setup or pixels.
for row in json.loads((Path(__file__).parent/'movie-native-param-results.json').read_text())['rows']:
 if row['sensor_mode'] not in ['0x1f','0xb5']:continue
 drive={'0x1f':4,'0xb5':0x94}[row['sensor_mode']]
 owner=h.run(0x637a6e88,0,drive,0);runtime=h.run(0x637a6c84,drive,0)
 h.u.mem_write(owner,DATA[owner-BASE:owner-BASE+0xc0]);h.put(op,123);h.put(op+8,0xba)
 for i,v in enumerate([drive,owner,runtime,0]):h.put(MEM+4*i,v)
 h.run(0x6379a510,op,123,MEM)
 h.u.mem_write(MEM+0x1000,bytes.fromhex(row['drv_param_hex']))
 for enc in [2,8]:
  h.u.mem_write(MEM+0x2000,bytes(0x34));h.put(MEM+0x2004,drive);h.put(MEM+0x2010,enc)
  h.run(0x6379cb68,123,MEM+0x1000,MEM+0x2000,0,0)
  records[-1].update(sensor=row['sensor_mode'],enc=enc)
assert len(records)==4 and all(r['compression_strategy']==2 for r in records)
print(json.dumps(dict(cases=len(records),mocks=['atexit','OS locks','logger','operation lookup returns constructed resource0x39','final native SetParams boundary'],native_driver_parameters=True,mmio_is_ram=True,rows=records),indent=2))
