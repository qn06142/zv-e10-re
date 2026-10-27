from pathlib import Path
import json,struct,hashlib
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB
from unicorn.arm_const import *
firmware=Path(r'D:/02_Development_And_Projects/pmca-re/dumps/firmware/av-cam.bin');b=firmware.read_bytes();base=0x635c6000
assert hashlib.md5(b).hexdigest()=='cdcae9d4fdbf66a33704a4c7564e346d'
u=Uc(UC_ARCH_ARM,UC_MODE_THUMB);u.mem_map(base,(len(b)+4095)&~4095);u.mem_write(base,b)
for a,n in [(0x40000000,0x20000),(0x50000000,4096),(0x60000000,0x20000)]:u.mem_map(a,n)
raw=0x40000000;dest=0x40001000
fixture=bytearray(0x140);fixture[0]=1;fixture[0xa]=2;fixture[0xc:0x10]=bytes([3,4,5,6]);struct.pack_into('<H',fixture,0x10,128);struct.pack_into('<I',fixture,0x2c,0x80)
for slot in range(4):struct.pack_into('<IH',fixture,0x24+64*slot,0x900+slot,0x300+slot)
u.mem_write(raw,bytes(fixture));cases=[]
for slot in range(4):
 u.mem_write(dest,b'\xa5'*64);u.reg_write(UC_ARM_REG_SP,0x60010000);u.reg_write(UC_ARM_REG_LR,0x50000001);u.reg_write(UC_ARM_REG_R0,dest);u.reg_write(UC_ARM_REG_R1,raw);u.reg_write(UC_ARM_REG_R2,slot)
 u.emu_start(0x6374ae89,0x50000000,count=1000);assert u.reg_read(UC_ARM_REG_PC)==0x50000000
 data=bytes(u.mem_read(dest,64));assert data[60:]==b'\xa5'*4
 assert struct.unpack_from('<I',data,4)[0]==0x900+slot and struct.unpack_from('<H',data,8)[0]==0x300+slot
 assert struct.unpack_from('<I',data,12)[0]==0x80 and data[0x30:0x32]==bytes([3,4])
 cases.append({'slot':slot,'width':struct.unpack_from('<H',data,0x18)[0],'height':struct.unpack_from('<H',data,0x1a)[0],'yc_compress_native':data[0x2f],'metadata_hex':data[:60].hex()})
assert [(c['width'],c['height'],c['yc_compress_native']) for c in cases]==[(3840,2160,1),(3840,2160,1),(1920,1080,1),(1280,720,0)]
result={'real_firmware_executed':True,'external_calls_stubbed':False,'camera_access':False,'geometry_is_offline_image_initial_data_not_camera_observation':True,'transfer_placement_and_unit_values_are_synthetic_input_tags_not_camera_measurements':True,'cases':cases}
out_path = Path(r'C:/Users/qn061/Documents/Codex/2026-10-22/chec/outputs/yc-source-re-20261025') if not Path('outputs/yc-source-re-20261025').is_dir() else Path('outputs/yc-source-re-20261025')
(out_path / 'vdf-metadata-builder-execution.json').write_text(json.dumps(result,indent=2));print('Real RTOS VDF metadata builder:',len(cases),'slots pass')
