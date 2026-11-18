"""Execute receiver SGC profile lookup and native split-frame geometry merge.
No buffer addresses, pixel production or hardware timing are simulated.
"""
import sys,json,argparse,struct
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('repo',type=Path);a=p.parse_args()
sys.path.insert(0,str(a.repo/'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness,MEM
from rtos import BASE,DATA
h=Harness()
provider=json.loads((Path(__file__).parent/'imager-provider-results.json').read_text())
rows=[];cases=0
for mode_row in provider['rows']:
 sensor=int(mode_row['sensor_mode'],16);profiles=[]
 for selector in range(32):
  h.u.mem_write(MEM,bytes(16));h.put(MEM,sensor);h.put(MEM+8,selector)
  ptr=h.run(0x6377f690,MEM);cases+=1
  if ptr:
   assert BASE<=ptr<BASE+len(DATA)-0x100
   profiles.append(dict(selector=hex(selector),address=hex(ptr),raw_hex=bytes(h.u.mem_read(ptr,0x100)).hex()))
 arcs=[]
 for split in [0,1]:
  h.u.mem_write(MEM+0x1000,bytes(40))
  status=h.run(0x637714d0,sensor,split,0,0,MEM+0x1000)
  arcs.append(dict(split=split,status=status,geometry_words=list(struct.unpack('<10I',h.u.mem_read(MEM+0x1000,40)))))
 rows.append(dict(sensor_mode=hex(sensor),inferred_fps=mode_row['inferred_fps'],profiles=profiles,arc_results=arcs))
by_id={int(r['sensor_mode'],16):r for r in rows}
for sensor,expected in [(0x1f,[6024,3392,0,0,6024,3392,12,8,6000,3376]),(0xb5,[4920,2776,0,0,4920,2776,12,8,4896,2760])]:
 r=by_id[sensor]
 assert r['arc_results'][0]['status']==11
 assert r['arc_results'][1]['status']==0 and r['arc_results'][1]['geometry_words']==expected
 assert {'0xa','0x1a'}<={x['selector'] for x in r['profiles']}
for sensor in [5,7]:
 r=by_id[sensor];assert r['arc_results'][0]['status']==0
 assert r['arc_results'][0]['geometry_words']==[2008,1134,0,0,2004,1134,4,6,1996,1122]
 assert r['arc_results'][1]['status']==11
native_params={int(r['sensor_mode'],16):r for r in json.loads((Path(__file__).parent/'movie-native-param-results.json').read_text())['rows']}
for sensor in [0x1f,0xb5,5,7]:
 raw=bytes.fromhex(native_params[sensor]['drv_param_hex'])
 width,height=struct.unpack_from('<I',raw,0x60)[0],struct.unpack_from('<I',raw,0x80)[0]
 arc=by_id[sensor]['arc_results'][int(sensor in [0x1f,0xb5])]
 assert arc['geometry_words'][8:10]==[width,height],(hex(sensor),width,height,arc)
print(json.dumps(dict(profile_cases=cases,arc_cases=46,mocks=[],lookup='0x6377f690',native_GetArcFrame='0x637714d0',native_merge='0x63d06f98',cadence_measured=False,pixel_buffers_identified=False,rows=rows),indent=2))
