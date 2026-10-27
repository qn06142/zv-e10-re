from pathlib import Path
import struct,json
from unicorn import *
from unicorn.arm_const import *
R=Path(r'D:/02_Development_And_Projects/pmca-re');B=Path('outputs/uvc-startup-fix/candidate-1080p/av-cam.bin').read_bytes();BASE=0x635c6000;O=Path('outputs/native-dmm-v28/provenance');O.mkdir(exist_ok=True)
u=Uc(UC_ARCH_ARM,UC_MODE_THUMB);u.mem_map(0x63000000,0x2000000);u.mem_write(BASE,B);u.mem_map(0x50000000,0x1000);u.mem_map(0x60000000,0x20000);u.mem_map(0x62000000,0x1000)
STACK=0x6001f000;STOP=0x50000000;META=0x60001000;STATE=0x60002000;CTX=0x60003000;MSG=0x60005000;OBJ=0x60006000;OBJ2=0x60007000;FRAME=0x60008000
RGS=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]
events=[];mock_handle=0x4321;expected_unit=0x295

def put(a,v):u.mem_write(a,struct.pack('<I',v&0xffffffff))
def word(a):return struct.unpack('<I',u.mem_read(a,4))[0]
def half(a):return struct.unpack('<H',u.mem_read(a,2))[0]
def ret(v=0):u.reg_write(UC_ARM_REG_R0,v);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
def hook(u,a,n,d):
 r=[u.reg_read(x) for x in RGS]
 if a==0x62000000:events.append({'service':'virtual_owner_getter'});ret(0x1234)
 elif a==0x635df710:
  assert r[0]==0x61003c and r[2]==0x50 and r[3]==1
  u.mem_write(MSG,bytes(80));put(r[1],MSG);events.append({'service':'native_message_allocate','queue':hex(r[0])});ret()
 elif a==0x636f2f4c:
  put(r[0],0);u.mem_write(r[1],struct.pack('<H',0x120));u.mem_write(r[2],bytes(2));put(r[3],0);ret()
 elif a==0x6375430c:
  raw=bytes(u.mem_read(r[0],24));assert half(r[0])==12 and word(r[0]+4)==expected_unit
  events.append({'service':'native_DMM_command_send','command':12,'type':hex(word(r[0]+4)),'wire':raw.hex()});ret()
 elif a==0x635df668:
  assert r[0]==0x61003c and r[1]==MSG
  raw=bytearray(80);struct.pack_into('<5H',raw,0,0x800c,0,mock_handle,0,1);struct.pack_into('<II',raw,16,0x2a000000,2073600);u.mem_write(MSG,bytes(raw));ret()
 elif a==0x635df72c:events.append({'service':'native_message_release'});ret()
 elif a==0x63cfed36:ret(r[0])
u.hook_add(UC_HOOK_CODE,hook)

def setup():
 u.reg_write(UC_ARM_REG_CPSR,0x30);u.reg_write(UC_ARM_REG_SP,STACK);u.reg_write(UC_ARM_REG_LR,STOP|1)
def run(start,end=STOP):
 u.emu_start(start|1,end,count=300000);assert u.reg_read(UC_ARM_REG_PC)==end,hex(u.reg_read(UC_ARM_REG_PC))
fields=json.loads((R/'research/firmware/raw_frame_source/verified_yc/field-layout.json').read_text())
rows=[]
for w,h,record,expected_unit,mock_handle in [(1920,1080,0x645b580c,0x295,0x4321),(1280,720,0x645b58ec,0x295,0x4321),(640,480,0x645b5924,0x295,0x4321),(1920,1080,0x645b580c,0x2a5,0x8765)]:
 original=word(record+40);put(record+40,expected_unit)
 events.clear();u.mem_write(META,b'\xa5'*60);u.mem_write(STATE,bytes(16));u.mem_write(CTX,bytes(0x200));u.mem_write(FRAME,bytes(64));u.mem_write(META+0x14,struct.pack('<HH',w,h))
 setup();u.reg_write(UC_ARM_REG_R4,META);u.reg_write(UC_ARM_REG_R7,STATE);u.reg_write(UC_ARM_REG_R8,record);run(0x6374cdd4,0x6374cf38)
 raw=bytes(u.mem_read(META,60));decoded={name:int.from_bytes(raw[off:off+n],'little') for name,off,n in fields}
 assert decoded['unit_type']==expected_unit and decoded['strip_width']==64 and decoded['unit_data_offset']==0
 assert decoded['yc_compress']==(0 if w==640 else 1)
 # Execute the actual consumer and actual native allocator, mocking only OSAL,
 # kernel reply and virtual owner getters. No guessed pixel or allocation code.
 put(OBJ,OBJ+0x100);put(OBJ+0x100,0x62000001);put(OBJ2,OBJ2+0x100);put(OBJ2+0x144,0x62000001);put(CTX+0x14,3)
 setup();u.reg_write(UC_ARM_REG_R4,META);u.reg_write(UC_ARM_REG_R5,OBJ2);u.reg_write(UC_ARM_REG_R6,CTX);u.reg_write(UC_ARM_REG_R8,record);u.reg_write(UC_ARM_REG_R9,OBJ);u.reg_write(UC_ARM_REG_R10,FRAME)
 run(0x6374d088,0x6374d0d2)
 assert word(CTX+0x18)==expected_unit and half(CTX+0x1c)==mock_handle
 assert word(META+4)==expected_unit and half(META+8)==mock_handle
 assert any(x.get('command')==12 and x.get('type')==hex(expected_unit) for x in events)
 rows.append({'taint_control':expected_unit!=0x295,'geometry':[w,h],'record':hex(record),'metadata_unit_type':hex(word(META+4)),'metadata_handle_matches_native_allocation_reply':True,'metadata_raw_hex':bytes(u.mem_read(META,60)).hex(),'confirmed_fields':{k:decoded[k] for k in ['unit_data_offset','canvas_size_x','canvas_size_y','valid_size_x','valid_size_y','target_size_x','target_size_y','data_site','iib_number','yc_compress','data_transfer','data_placement','data_content','data_scan','strip_width']},'untouched_fields_not_inferred':['yc_bit_depth','aspect','cam_freq_char_h'],'events':list(events)})
 put(record+40,original)
report={'original_RTOS_basic_blocks_and_allocator_executed':True,'hardware_allocation_services_mocked':True,'complete_configuration_routine_not_executed':True,'pixel_format_enum_meanings_not_inferred':True,'camera_access':False,'firmware_md5':'90096db2c76148f4f9db5d104e5c608c','cases':rows}
(O/'vef295-allocation-metadata-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
