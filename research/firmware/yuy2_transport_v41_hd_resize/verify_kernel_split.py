"""Execute the installed driver's original size-derived staging split."""
from pathlib import Path
import json,struct
from elftools.elf.elffile import ELFFile
from unicorn import *
from unicorn.arm_const import *
u=Uc(UC_ARCH_ARM,UC_MODE_ARM);base=0x10000000
with Path('.local/outputs/vga-v40/usbg_video.ko').open('rb') as f:b=ELFFile(f).get_section_by_name('.text').data()
u.mem_map(base,0x10000);u.mem_write(base,b);u.mem_map(0x40000000,0x10000)
def put(a,v):u.mem_write(a,struct.pack('<I',v))
def get(a):return struct.unpack('<I',u.mem_read(a,4))[0]
rows=[]
for size in [1843200,8388608,12582912]:
 state=0x40000000;frame=state+0x8000;physical=0x12000000;virtual=0xd2000000
 u.reg_write(UC_ARM_REG_CPSR,0x10)
 for reg,v in [(UC_ARM_REG_R4,state),(UC_ARM_REG_R5,1),(UC_ARM_REG_R6,0),(UC_ARM_REG_R7,physical),(UC_ARM_REG_R0,virtual),(UC_ARM_REG_R11,frame)]:u.reg_write(reg,v)
 put(frame-0x24,size);u.emu_start(base+0x1b44,base+0x1b6c,count=100)
 assert get(state)==virtual and get(state+4)==physical and get(state+8)==virtual+size//2 and get(state+12)==physical+size//2 and get(state+0xa4)==size
 rows.append({'returned_allocation_bytes':size,'slot_bytes':size//2,'full_HD_frame_plus_header_fits':size//2>=4147200+12})
assert not rows[0]['full_HD_frame_plus_header_fits'] and rows[1]['full_HD_frame_plus_header_fits']
out={'original_kernel_instructions_executed':True,'kernel_md5':'388799d95bbb524ca581c66b077b6dc2','slice':['.text+0x1b44','.text+0x1b6c'],'hardware_calls_executed':False,'cases':rows};Path('.local/outputs/hd-v41/kernel-split-verification.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
