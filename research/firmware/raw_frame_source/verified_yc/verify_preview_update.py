from pathlib import Path
Path("outputs/yc-live-20261026").mkdir(parents=True,exist_ok=True)
import struct,json,hashlib
from unicorn import *
from unicorn.arm_const import *
B=Path(r'D:/02_Development_And_Projects/pmca-re/dumps/firmware/av-cam.bin').read_bytes();BASE=0x635c6000
assert hashlib.md5(B).hexdigest()=='cdcae9d4fdbf66a33704a4c7564e346d'
u=Uc(UC_ARCH_ARM,UC_MODE_THUMB);u.mem_map(BASE,(len(B)+4095)&~4095);u.mem_write(BASE,B)
for a,n in [(0x40000000,0x20000),(0x50000000,0x2000),(0x60000000,0x20000)]:u.mem_map(a,n)
STUB=0x50001000;STOP=0x50000000;ACC=0x40000000;VT=0x40000100;MSG=0x40000200;RAW=0x40001000
u.mem_write(ACC,struct.pack('<I',VT));u.mem_write(VT+8,struct.pack('<I',STUB|1));u.mem_write(MSG+8,struct.pack('<II',RAW,0));stubcalls=[]
from collections import deque
last=deque(maxlen=35)
def hook(u,a,n,d):
 last.append(hex(a))
 if a==0x635dfab4:
  value=u.reg_read(UC_ARM_REG_R0);assert 0x40000000<=value<0x40020000,hex(value)
  stubcalls.append('OSAL memory mapping: fixture identity mapping only; no real address translation')
  u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR));return
 if a==STUB:
  assert u.reg_read(UC_ARM_REG_R0)==ACC
  stubcalls.append('MsgAccessor::GetMessage fixture accessor');u.reg_write(UC_ARM_REG_R0,MSG);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
u.hook_add(UC_HOOK_CODE,hook)
def run(adr,*args):
 u.reg_write(UC_ARM_REG_SP,0x60010000);u.reg_write(UC_ARM_REG_LR,STOP|1)
 for r,v in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],args):u.reg_write(r,v)
 try:u.emu_start(adr|1,STOP,count=50000)
 except Exception:
  print('PC',hex(u.reg_read(UC_ARM_REG_PC)),'last',list(last));raise
 assert u.reg_read(UC_ARM_REG_PC)==STOP
 return u.reg_read(UC_ARM_REG_R0)
rows=[]
for width,height,content in [(640,480,2),(640,480,1),(640,480,0),(1920,1080,2),(1280,720,2)]:
 raw=bytearray(216);raw[:4]=b'SSYC';struct.pack_into('<III',raw,8,1,3,32)
 for at,cat,data,size,nxt in [(32,0,64,64,128),(128,1,160,8,168),(168,2,200,16,0)]:
  raw[at:at+4]=b'ETRY';struct.pack_into('<I',raw,at+4,cat);struct.pack_into('<III',raw,at+12,data,size,nxt)
 image=64
 for off in [0x14,0x18,0x20,0x28]:struct.pack_into('<H',raw,image+off,width)
 for off in [0x16,0x1a,0x22,0x2a]:struct.pack_into('<H',raw,image+off,height)
 raw[image]=1;raw[image+0x32]=content;raw[image+0x31]=0x77;raw[image+0x2f]=0x88
 struct.pack_into('<II',raw,208,0x100,0x20)
 u.mem_write(RAW,bytes(raw));result=run(0x6372f54c,0,0,ACC,0)
 final=bytes(u.mem_read(RAW,216));m=final[64:124]
 rows.append(dict(width=width,height=height,data_content=content,return_value=result,canvas_size_y=struct.unpack_from('<H',m,0x1a)[0],valid_size_y=struct.unpack_from('<H',m,0x22)[0],target_size_y=struct.unpack_from('<H',m,0x2a)[0],data_placement=m[0x31],yc_compress=m[0x2f],data_site=m[0x2c],author=final[165],camera_info_plus8=struct.unpack_from('<I',final,208)[0],metadata_hex=m.hex()))
 print(rows[-1])
 if content==2:assert rows[-1]['canvas_size_y']==height and m[0x31]==1
 else:assert rows[-1]['canvas_size_y']==height//2 and m[0x31]==0
 assert result==0 and final[165]==1
report=dict(actual_Sony_function_executed='0x6372f54c VdfInputCmdUpdateYuvPin::changeSSYCData',stubs=sorted(set(stubcalls)),real_native_SDS_parser_and_geometry_lookup_executed=True,camera_access=False,pixel_packing_proved=False,cases=rows)
Path('outputs/yc-live-20261026/preview-metadata-execution.json').write_text(json.dumps(report,indent=2))
