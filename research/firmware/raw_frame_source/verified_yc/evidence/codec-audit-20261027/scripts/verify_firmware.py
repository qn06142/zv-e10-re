from pathlib import Path
import struct,json,hashlib
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_HOOK_CODE
from unicorn.arm_const import *
B=Path('outputs/uvc-startup-fix/candidate-1080p/av-cam.bin').read_bytes();BASE=0x635c6000
u=Uc(UC_ARCH_ARM,UC_MODE_THUMB);u.mem_map(0x63000000,0x2000000);u.mem_write(BASE,B)
u.mem_map(0x50000000,4096);u.mem_map(0x60000000,0x20000)
STOP=0x50000000;OBJ=0x60001000;CTX=0x60002000;STACK=0x6001f000
# Only logging is replaced; the original conditions, branches and returns run.
def hook(u,a,n,d):
 if a in (0x63c5fe48,0x63a427a8,0x63a42820):
  u.reg_write(UC_ARM_REG_R0,0);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
u.hook_add(UC_HOOK_CODE,hook)
def put(a,v):u.mem_write(a,struct.pack('<I',v))
def run(pc,args,stop=STOP):
 u.reg_write(UC_ARM_REG_CPSR,0x30);u.reg_write(UC_ARM_REG_SP,STACK);u.reg_write(UC_ARM_REG_LR,STOP|1)
 for r,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):u.reg_write(r,v)
 u.emu_start(pc|1,stop,count=100000);assert u.reg_read(UC_ARM_REG_PC)==stop
 return u.reg_read(UC_ARM_REG_R0)
alignment=[]
for mirror in range(4):
 for compress in (0,1):
  for offset,width in [(0,1920),(0,1440),(32,1440),(0,1472)]:
   u.mem_write(OBJ,bytes(0x200));u.mem_write(OBJ+0x30,struct.pack('<H',offset));u.mem_write(OBJ+0x34,struct.pack('<H',width))
   ret=run(0x63a460d4,(0,OBJ,mirror,compress))
   expected=5 if mirror in (1,3) and compress==1 and (offset+width)%64 else 0
   assert ret==expected,(mirror,compress,offset,width,ret)
   alignment.append(dict(mirror=mirror,compress=compress,offset=offset,width=width,result=ret))
strip=[]
for func in (0x63a37f3c,0x63a3ad04):
 for mode in range(1,6 if func==0x63a37f3c else 9):
  u.mem_write(CTX,bytes(0x200));put(CTX+0x104,mode);u.mem_write(CTX+0x98,struct.pack('<H',1730))
  ret=run(func,(0,OBJ,CTX,0));strip.append(dict(function=hex(func),mode=mode,result=ret))
geometry=[]
for index in (0,1,4,5):
 record=0x645b580c+index*56
 raw=B[record-BASE:record-BASE+56]
 geometry.append(dict(index=index,record=hex(record),record_flag=struct.unpack_from('<h',raw,2)[0],valid=list(struct.unpack_from('<HH',raw,20)),canvas=list(struct.unpack_from('<HH',raw,24)),unit_type=hex(struct.unpack_from('<I',raw,40)[0])))
# Execute original metadata writer for compressed HD + uncompressed VGA; width=64
# is written regardless of yc_compress, so it cannot identify compressed bytes.
metadata=[]
for index in (0,1,4,5):
 record=0x645b580c+index*56
 u.mem_write(OBJ,b'\xa5'*60);u.mem_write(CTX,bytes(16))
 u.reg_write(UC_ARM_REG_R4,OBJ);u.reg_write(UC_ARM_REG_R7,CTX);u.reg_write(UC_ARM_REG_R8,record)
 run(0x6374cdd4,(),0x6374cf38)
 raw=bytes(u.mem_read(OBJ,60))
 metadata.append(dict(index=index,yc_compress=raw[47],strip_width=struct.unpack_from('<H',raw,52)[0],yc_bit_depth_untouched=raw[54]==0xa5,valid=list(struct.unpack_from('<HH',raw,32)),canvas=list(struct.unpack_from('<HH',raw,24))))
 assert metadata[-1]['strip_width']==64 and metadata[-1]['yc_compress']==(0 if index==5 else 1)
 assert metadata[-1]['yc_bit_depth_untouched']
result={'firmware_md5':hashlib.md5(B).hexdigest(),'camera_access':False,'original_ARM_instructions_executed':True,'logging_only_mocked':True,'alignment_cases':alignment,'strip_width_enum_results':strip,'geometry_table_records':geometry,'metadata_execution':metadata,'limits':'Static code/configuration behavior only; active packet descriptor and codec syntax not established'}
Path('outputs/yc-codec-audit/firmware-verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='alignment_cases'},indent=2));print('alignment cases passed:',len(alignment))
