"""Offline alias-only DMM candidate: preserve every physical-pool definition."""
from pathlib import Path
import hashlib,json,struct
R=Path('D:/02_Development_And_Projects/pmca-re');O=Path('.local/outputs/hd-v41');O.mkdir(exist_ok=True)
b=(R/'.local/dumps/camera_2025/usr/setting/DmmConfig.bin').read_bytes();assert hashlib.md5(b).hexdigest()=='9f197ff9b300e49ab531b6f9e794253e'
assert struct.pack('<4I',0xffffffff,0x127,0,0x165) in b
hd_sizes=[struct.unpack_from('<5I',b,a)[4] for a in range(0x1000,0x10000,4) if struct.unpack_from('<5I',b,a)[0]&255==15 and struct.unpack_from('<5I',b,a)[3]==0x165]
assert hd_sizes and min(hd_sizes)==4147200
frame=1920*1080*2;slots=2*(frame+12);out=bytearray(b);edits=[]
# Existing native HD pool 0x165 (logical 0x127); existing 8MiB pool 0x1ba (logical 0x17c).
for off,unit,old,new in [(0x13094,0x50e,0x589,0x1ba)]:
 assert struct.unpack_from('<4I',b,off)==(unit,0,old,0xffffffff)
 sizes=[]
 for a in range(0x1000,0x10000,4):
  attr,parent,kind,pool,size=struct.unpack_from('<5I',b,a)
  if pool==new and attr&255==15:sizes.append(size)
 assert sizes and min(sizes)>=(slots if unit==0x50e else frame)
 struct.pack_into('<I',out,off+8,new);edits.append({'unit':hex(unit),'word_offset':hex(off+8),'old_pool':hex(old),'new_pool':hex(new),'configured_min_bytes':min(sizes)})
allowed={e+q for e in [0x1309c] for q in range(4)}
assert all(a==c or i in allowed for i,(a,c) in enumerate(zip(b,out)));assert len(b)==len(out)
O.joinpath('DmmConfig.bin').write_bytes(out)
report={'offline_only':True,'installed':False,'baseline_md5':hashlib.md5(b).hexdigest(),'output_md5':hashlib.md5(out).hexdigest(),'frame_bytes':frame,'two_usb_slots_including_headers':slots,'physical_pool_sizes_changed':False,'image_allocation_unit':'0x127','image_pool':'0x165','alias_edits':edits,'limits':['Configured capacity does not prove live availability or simultaneous allocation.','Both source and destination request exclusive native allocations from the same existing HD pool; failure must refuse streaming.','Only USB unit0x50e alias is changed; cold-boot and live allocation verification are required before hardware use.']}
O.joinpath('memory-plan.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
