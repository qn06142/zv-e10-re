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
records=[];raw_calls=[];logs=[];raw_mmio_writes=[]
def observe_common(args):
 records.append(dict(param=bytes(h.u.mem_read(args[2],0x28)).hex(),parameter_table=hex(h.word(args[2])),header_table=hex(h.word(op+0x14))))
 # Observation only: execute original 0x6379a57c after this hook.
def observe_raw(args):
 header_table=h.word(args[1]+4)
 raw_calls.append(dict(header_table=hex(header_table),raw_geometry=hex(h.word(header_table+0x5c)),buffer=hex(h.word(args[2]+0x14)),capacity=h.word(args[2]+0x18)))
 # Observation only: execute original 0x6379e2b8 after this hook.
h.callbacks[0x6379a57c]=observe_common
h.callbacks[0x6379e2b8]=observe_raw
from rtos import cstr
h.callbacks[0x6396f8c4]=lambda args:(logs.append(cstr(args[0])),h.ret(0))
from unicorn import UC_HOOK_MEM_WRITE
h.u.hook_add(UC_HOOK_MEM_WRITE,lambda u,access,address,size,value,data:raw_mmio_writes.append((address,size,value)),begin=0xfc0a8000,end=0xfc0a9fff)
# Force the extra RAW writer flag only inside Unicorn, with the native default
# header and parameter tables. Buffer address/capacity are controlled fixtures.
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
  h.put(MEM+0x2008,0x20000000);h.put(MEM+0x2014,1);h.put(MEM+0x2018,0x4000000)
  h.put(op+0x28,h.word(op+0x28)|0x200000)
  h.run(0x6379cb68,123,MEM+0x1000,MEM+0x2000,1,0)
  records[-1].update(sensor=row['sensor_mode'],enc=enc)
assert len(records)==len(raw_calls)==4
assert all(r['raw_geometry']=='0x0' and r['buffer']=='0x20000000' and r['capacity']==0x4000000 for r in raw_calls)
assert all(r['parameter_table']!=r['header_table'] for r in records)
assert len(logs)==4 and all(x=='IMG:DfeCamAif%d: SgcParam Not Found' for x in logs)
assert raw_mmio_writes==[]
print(json.dumps(dict(cases=len(records),mocks=['atexit','OS locks','logger','operation lookup returns constructed resource0x39'],final_SetParams_original=True,raw_setup_original=True,extra_RAW_flag_forced_in_emulator=True,buffer_address_and_capacity_are_fixtures=True,raw_mmio_writes=raw_mmio_writes,logs=logs,rows=records,raw_calls=raw_calls),indent=2))
