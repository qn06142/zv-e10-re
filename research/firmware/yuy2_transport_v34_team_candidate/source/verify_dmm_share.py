"""Run original Sony kernel Share handler and reference checks; no camera access."""
from pathlib import Path
import struct,json,hashlib
from elftools.elf.elffile import ELFFile
from unicorn import *
from unicorn.arm_const import *
P=Path(r'D:/02_Development_And_Projects/pmca-re/.local/dumps/camera_2025/usr/usr/kmod/dmm.ko')
with P.open('rb') as f:TEXT=ELFFile(f).get_section_by_name('.text').data()
BASE=0x10000000;TABLE=0x40000000;MEM=0x50000000;STOP=0x60000000;STACK=0x70010000
HANDLE=0x1755;TYPE=0xe0b00;rows=[]
def case(name,state,refs,serial=None,typ=TYPE,handle=HANDLE):
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
 for p,n in [(BASE,(len(TEXT)+4095)&~4095),(TABLE,0x100000),(MEM,0x10000),(STOP,4096),(STACK-0x10000,0x20000)]:u.mem_map(p,n)
 u.mem_write(BASE,TEXT);u.mem_write(BASE+0x88e8,struct.pack('<I',TABLE));u.mem_write(BASE+0x93e8,struct.pack('<I',TABLE))
 # Resolve only the handler's Share relocation to the real internal function.
 u.mem_write(BASE+0x634c,struct.pack('<I',0xeb000000|((0x884c-0x634c-8)>>2)&0xffffff))
 u.mem_write(BASE+0x6388,struct.pack('<I',0xeb000000|((0x9238-0x6388-8)>>2)&0xffffff))
 index=(handle&0x3ff)+((handle>>15)<<10);entry=TABLE+index*0x150
 def w(p,fmt,*v):u.mem_write(p,struct.pack(fmt,*v))
 w(entry+0xb18,'<I',typ);w(entry+0xb20,'<B',refs);w(entry+0xb23,'<B',(handle>>10)&31 if serial is None else serial);w(entry+0xb24,'<H',state)
 before=bytes(u.mem_read(entry+0xb18,16));req=MEM;reply=MEM+256
 w(req+4,'<I',0x12345555);w(req+0xc,'<HHI',2,handle,TYPE);w(req+0x20,'<HH',0x611a,0)
 access=[]
 def hook(u,pc,size,data):
  if pc==BASE+0x9238:
   access.append([u.reg_read(x) for x in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]])
  if pc in [BASE+0x928c,BASE+0x92f8]:
   u.reg_write(UC_ARM_REG_R0,0);u.reg_write(UC_ARM_REG_R1,0);u.reg_write(UC_ARM_REG_PC,pc+4)
 u.hook_add(UC_HOOK_CODE,hook)
 for r,v in [(UC_ARM_REG_SP,STACK),(UC_ARM_REG_LR,STOP),(UC_ARM_REG_R0,req),(UC_ARM_REG_R1,reply),(UC_ARM_REG_R2,2)]:u.reg_write(r,v)
 u.emu_start(BASE+0x62e4,STOP,count=10000);assert u.reg_read(UC_ARM_REG_PC)==STOP
 raw=bytes(u.mem_read(reply,24));status=struct.unpack_from('<h',raw,2)[0];native=struct.unpack_from('<h',raw,10)[0];after=bytes(u.mem_read(entry+0xb18,16));count=after[8]
 if status<0:assert before==after,(name,before.hex(),after.hex())
 else:assert count==refs+1,(name,count)
 assert len(access)==1 and access[0][0]==handle
 row=dict(case=name,status=status,native_status=native,references_before=refs,references_after=count,reply_hex=raw.hex(),reference_state_unchanged_on_failure=status<0,access_info_original_code=True)
 rows.append(row);return row
for state in [0,4]:
 r=case('unshareable_state_'+str(state),state,1);assert r['status']==-1 and r['native_status']==-1
r=case('saturated_reference_count',2,255);assert r['status']==-1 and r['native_status']==-1
for state in [1,2,3]:r=case('active_state_'+str(state),state,1);assert r['status']==0
r=case('maximum_successful_count',2,254);assert r['status']==0 and r['references_after']==255
r=case('wrong_type',2,1,typ=TYPE+1);assert r['status']==-3 and r['native_status']==-3
r=case('stale_serial',2,1,serial=6);assert r['status']==-5 and r['native_status']==-517
r=case('invalid_index',2,1,handle=0xffff);assert r['status']==-5 and r['native_status']==-261
captured=json.loads(Path('.local/outputs/vga-v32/capture-first-01/logs/source-share-reply.json').read_text())['raw_reply_hex']
assert rows[0]['reply_hex']==captured and rows[2]['reply_hex']==captured
out=dict(camera_access=False,original_kernel_instructions_executed=True,kernel_md5=hashlib.md5(P.read_bytes()).hexdigest(),passed=len(rows),cases=rows,conclusion='Captured native -1 is unshareable state or reference saturation; Share does not increment a reference on these failures.',limitations=['Clock/debug-table imports mocked; access-info function executed with zero attached extents.','Which rejection condition occurred on camera is not known.'])
Path('.local/outputs/vga-v34/kernel-share-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
