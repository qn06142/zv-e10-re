"""Execute original libmpr recording-depth API core and record-entry helper offline."""
from pathlib import Path
import importlib.util,json,struct
from unicorn import *
from unicorn.arm_const import *
spec=importlib.util.spec_from_file_location('support','.local/work/vga-v40/recipe/verify_support.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
u=Uc(UC_ARCH_ARM,UC_MODE_ARM);base=0x08000000
m.load(u,Path('D:/02_Development_And_Projects/pmca-re/.local/dumps/camera_2025/usr/usr/lib/libmpr.so'),base,lambda n:0x10000000)
u.mem_map(0x40000000,0x40000);u.mem_map(m.STOP,4096);u.mem_map(0x60000000,0x20000)
obj=0x40000000;params=obj+0x10000;dest=obj+0x20000

def run(off,*args):
 u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,m.STACK);u.reg_write(UC_ARM_REG_LR,m.STOP)
 for i,a in enumerate(args):
  if i<4:u.reg_write(m.R[i],a)
  else:m.put(u,m.STACK+4*(i-4),a)
 u.emu_start(base+off+1,m.STOP,count=30000);assert u.reg_read(UC_ARM_REG_PC)==m.STOP
 return u.reg_read(UC_ARM_REG_R0)
rows=[]
for state,depth,channel_state,expected in [(3,0,1,0),(3,1,1,0),(4,1,5,0),(3,2,1,0),(3,3,1,5),(2,1,1,10),(3,1,0,10)]:
 u.mem_write(obj,bytes(0x4000));m.put(u,obj+0x2cc,state);m.put(u,obj+0x179c,channel_state);m.put(u,obj+0x176c,0xa5a5a5a5)
 u.mem_write(params,struct.pack('<II',0,depth))
 rc=run(0x5420dc,obj,params,1);assert rc==expected,(state,depth,channel_state,rc)
 got=m.word(u,obj+0x176c);assert got==(depth if rc==0 else 0xa5a5a5a5)
 rows.append({'object_state':state,'requested_depth_enum':depth,'channel_state':channel_state,'returncode':rc,'stored_word':got})
for content,depth,expected in [(0x100,0,0),(0x100,1,1),(0x100,2,2),(0,1,255)]:
 u.mem_write(dest,bytes(256));run(0x54917e,obj,dest,content,7,depth)
 assert m.word(u,dest+0xec)==expected
 rows.append({'record_entry_content':content,'requested_depth_enum':depth,'entry_depth_ec':m.word(u,dest+0xec),'entry_color_e8':m.word(u,dest+0xe8)})
# Execute the original RecStart slice that reads the channel cache into MovieRecParam.
cache_cases=[]
for channel in range(4):
 for depth in range(3):
  u.mem_write(dest,bytes(0x400));m.put(u,dest,channel*0x108)
  m.put(u,obj+channel*0x108+0x176c,depth)
  u.reg_write(UC_ARM_REG_R4,obj);u.reg_write(UC_ARM_REG_R7,dest)
  u.reg_write(UC_ARM_REG_CPSR,0x10)
  u.emu_start(base+0x5436b4+1,base+0x5436ea,count=100)
  assert u.reg_read(UC_ARM_REG_PC)==base+0x5436ea
  assert m.word(u,dest+0x90)==depth
  cache_cases.append({'channel':channel,'depth':depth,'MovieRecParam_offset_6c':m.word(u,dest+0x90)})
# Enumerate the original codec-quality mapper without hardware calls.
quality_cases=[]
for quality in range(42):
 for color in range(2):
  values=[]
  for depth in range(3):
   u.mem_write(dest,b'\xa5');rc=run(0x8a4438,quality,color,depth,dest)
   values.append({'depth':depth,'returncode':rc,'codec_quality_byte':u.mem_read(dest,1)[0]})
  quality_cases.append({'MPR_quality':quality,'color_enum':color,'depth_results':values})
assert len(quality_cases)==84
assert all((x['depth_results'][0]['returncode'],x['depth_results'][0]['codec_quality_byte'])==(x['depth_results'][2]['returncode'],x['depth_results'][2]['codec_quality_byte']) for x in quality_cases)
assert any(x['depth_results'][0]['codec_quality_byte']!=x['depth_results'][1]['codec_quality_byte'] for x in quality_cases)
Path('.local/outputs/yc-producer-depth-20261030/codec-quality-depth-table.json').write_text(json.dumps(quality_cases,indent=2))
pub_cases=[]
for quality in range(42):
 for color in range(2):
  for flag in range(2):
   values=[run(0x737fbc,quality,flag,0x100,color,depth) for depth in range(3)]
   pub_cases.append({'MPR_quality':quality,'color_enum':color,'bool_arg':flag,'public_quality_by_depth_0_1_2':values})
assert all(x['public_quality_by_depth_0_1_2'][0]==x['public_quality_by_depth_0_1_2'][2] for x in pub_cases)
assert any(x['public_quality_by_depth_0_1_2'][0]!=x['public_quality_by_depth_0_1_2'][1] for x in pub_cases)
Path('.local/outputs/yc-producer-depth-20261030/public-quality-depth-table.json').write_text(json.dumps(pub_cases,indent=2))
enum_names=[]
for value in [0,1,2,3]:
 ptr=run(0x899774,0,value);enum_names.append({'value':value,'label':m.cstr(u,ptr)})
assert [x['label'] for x in enum_names]==['8bit','10bit','12bit','unknown']
out={'camera_access':False,'original_Linux_instructions_executed':True,'core_setter':'libmpr.so+0x5420dc','cached_field':'object+0x176c+channel*0x108','record_entry_helper':'libmpr.so+0x54917e','cases':rows,'RecStart_cache_copy_cases':cache_cases,'codec_quality_original_cases':252,'public_quality_original_cases':504,'MPR_depth_names':enum_names,'limitations':['Context/channel states and inputs are controlled fixtures.','No external hardware or IPC is invoked by these core helpers.','Named 12-bit configuration support does not prove the active camera YC producer emits 12-bit samples.','A cached field or recorder-entry parameter does not by itself prove an ISP/YC producer change.']}
Path('.local/outputs/yc-producer-depth-20261030/record-depth-api-verification.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
