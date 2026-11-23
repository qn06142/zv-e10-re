from pathlib import Path
import io,runpy,contextlib,struct,json
from elftools.elf.elffile import ELFFile
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *
with contextlib.redirect_stdout(io.StringIO()):old=runpy.run_path('.local/work/yc-frame-contract-20261029/verify_usb_lifetime.py')
p=Path('.local/outputs/vga-v37/usbg_video.ko');e=ELFFile(io.BytesIO(p.read_bytes()));B=old['B'];S=old['S'];D=old['D'];O=old['O'];X=0x300000;STOP=old['STOP'];rows=[]
machine=old['machine'];machine.__globals__['code']=e.get_section_by_name('.text').data();sy=e.get_section_by_name('.symtab')
indices={s.name:i for i,s in enumerate(e.iter_sections())};bases={indices['.text']:B,indices['.text.yc37_fence']:X}
def relocate(u):
 u.mem_map(X,4096);u.mem_write(X,e.get_section_by_name('.text.yc37_fence').data())
 for rn in ['.rel.text','.rel.text.yc37_fence']:
  sec=e.get_section_by_name(rn);start=bases[sec['sh_info']]
  for r in sec.iter_relocations():
   s=sy.get_symbol(r['r_info_sym'])
   if rn=='.rel.text' and not s.name.startswith('__yc37_'):continue
   assert r['r_info_type']==29
   at=start+r['r_offset'];w=old['word'](u,at);a=(w&0xffffff)<<2
   if a&0x2000000:a-=0x4000000
   v=bases[s['st_shndx']]+s['st_value']+a-at
   assert v%4==0 and -0x2000000<=v<0x2000000
   old['put'](u,at,(w&0xff000000)|((v>>2)&0xffffff))
for name in ['complete','timeout','start_failure','busy']:
 u=machine();relocate(u);old['put'](u,D,int(name=='complete'));u.reg_write(UC_ARM_REG_R5,D);u.reg_write(UC_ARM_REG_R7,614400);unlocks=[];visits=[]
 def hook(u,pc,size,_):
  off=pc-B;visits.append(off)
  if off==0x10d0:u.emu_stop();return
  if off in [0xf90,0xfbc,0xff0,0x1018,0xfd4,0x1048,0x1050,0x105c,0x10b4,0x10bc]:
   if off==0x10bc:unlocks.append(1)
   u.reg_write(UC_ARM_REG_R0,O if off in [0x1050,0x105c,0x10b4] else 0);u.reg_write(UC_ARM_REG_PC,pc+4)
 u.hook_add(UC_HOOK_CODE,hook)
 start=0xf88
 if name=='start_failure':
  start=0xf74;u.reg_write(UC_ARM_REG_R0,0xffffffff);u.reg_write(UC_ARM_REG_R4,O);u.reg_write(UC_ARM_REG_R6,12)
 if name=='busy':
  start=0xf04;u.mem_write(S+0x10,b'\1\1');u.reg_write(UC_ARM_REG_R5,S)
 u.emu_start(B+start,STOP,count=2000);assert u.reg_read(UC_ARM_REG_PC)==B+0x10d0
 rc=u.reg_read(UC_ARM_REG_R0);rc=rc if rc<0x80000000 else rc-0x100000000
 assert rc==dict(complete=0,timeout=-110,start_failure=-5,busy=-16)[name]
 flags=list(u.mem_read(S+0x10,2));assert flags==dict(complete=[1,0],timeout=[0,0],start_failure=[0,0],busy=[1,1])[name]
 assert len(unlocks)==1
 rows.append(dict(case=name,return_signed=rc,slot_flags=flags,unlock_calls=len(unlocks),slot_bytes=old['word'](u,S+0x1c)))
out=dict(camera_access=False,compiled_arm_with_new_cross_section_relocations=True,cases=rows,limitations=['Scheduler, locks, get-this and diagnostics are controlled stubs.','No real kernel loader, DMA, UDC or disconnect race emulated.'])
Path('.local/outputs/vga-v37/kernel-fence-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
