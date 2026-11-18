import sys,runpy,contextlib,io,json,struct
from pathlib import Path
with contextlib.redirect_stdout(io.StringIO()):ctx=runpy.run_path(str(Path(__file__).parent/'verify_imager_provider.py'))
h=ctx['h'];MEM=ctx['MEM'];drv=MEM;req=MEM+0x1000;out=MEM+0x2000
rows=[]
for sensor in [0x1f,0xb5,0x89,0x13,0xb4,0x5,0x7,0xf]:
 h.u.mem_write(req,bytes(0x30));h.put(req,sensor)
 h.u.mem_write(out,bytes([0xcd])*0x160)
 status=h.run(0x63d2b012,drv,0,req,out)
 assert status==0,(hex(sensor),status)
 rows.append(dict(sensor_mode=hex(sensor),status=status,compress_type=h.word(out+0x34),H=h.word(out+0x38),V=h.word(out+0x3c),vd_num=struct.unpack('<H',h.u.mem_read(out+0x18,2))[0],drv_param_hex=bytes(h.u.mem_read(out,0x14c)).hex()))
by_id={int(r['sensor_mode'],16):r for r in rows}
assert all(by_id[x]['compress_type']==3 and by_id[x]['vd_num']==2 for x in [0x1f,0xb5,0x89,0x13,0xb4])
assert all(by_id[x]['compress_type']==0 and by_id[x]['vd_num']==1 for x in [5,7,15])
print(json.dumps(dict(cases=len(rows),mocks=['atexit registration','logger'],query='0x63d2b012',rows=rows),indent=2))
