"""Execute sensor-mode normalization and DFE mode lookup, without guessing cadence."""
import sys,json,argparse
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('repo',type=Path);a=p.parse_args()
sys.path.insert(0,str(a.repo/'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness,MEM
h=Harness();logs=[]
h.callbacks[0x6396f8c4]=lambda args:(logs.append(args[0]),h.ret(0))
h.run(0x637a6d90)
packet=json.loads((Path(__file__).parent/'mipi-results.json').read_text())
by_drive={int(x['drive_mode'],16):x for x in packet['results']}
rows=[]
for sensor in range(1,219):
 logs.clear()
 normalized=h.run(0x638cf8b0,sensor)
 drive=h.run(0x638ce894,0,normalized)
 rid=h.run(0x637a6d78,drive,MEM) if drive<149 else 0
 # A nonnull family pointer is NOT a supported-mode check: fallback exists.
 family=h.run(0x637a6c84,drive,0)
 row=dict(sensor_mode=hex(sensor),normalized_mode=hex(normalized),drive_mode=hex(drive),resource=hex(rid),family=hex(family),diagnostic_count=len(logs))
 if rid:
  assert drive in by_drive
  row['native_bit_length']=by_drive[drive]['native_bit_length']
  row['vc0_data_type']=by_drive[drive]['vc0_data_type']
 rows.append(row)
# Execute original decoder including unknown-type diagnostics, not just return values.
obj=MEM+0x4000;regs=MEM+0x5000;h.put(obj+4,regs)
for dt,bits in [(0x2b,10),(0x2c,12),(0x2d,14),(0x30,4),(0x31,8),(0x2e,14),(0x3f,14)]:
 logs.clear();h.put(regs+0x84,dt)
 assert h.run(0x637a277c,obj)==bits
 assert len(logs)==(0 if dt in [0x2b,0x2c,0x2d,0x30,0x31] else 1)
# All unsupported drives use a nonnull fallback; do not count this as an available source.
assert h.run(0x637a6c84,0xba,0)!=0
print(json.dumps(dict(cases=len(rows),mocks=['logger'],supported_cases=sum(bool(int(r['resource'],16)) for r in rows),cadence_proven=False,rows=rows),indent=2))
