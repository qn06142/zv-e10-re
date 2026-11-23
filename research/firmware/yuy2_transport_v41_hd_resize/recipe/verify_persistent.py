from pathlib import Path
import argparse,io,json,struct
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_HOOK_CODE
from unicorn.arm_const import *
import persistent_stream as patch
ap=argparse.ArgumentParser();ap.add_argument('--stock',type=Path,required=True);ap.add_argument('--candidate',type=Path,required=True);ap.add_argument('--module',type=Path,required=True);a=ap.parse_args()
stock=a.stock.read_bytes();data=a.candidate.read_bytes();built,report=patch.build(stock);assert built==data
e=ELFFile(io.BytesIO(data));old=ELFFile(io.BytesIO(stock));module=ELFFile(io.BytesIO(a.module.read_bytes()));results=[]
assert not any(t.entry.d_tag in ['DT_INIT','DT_INIT_ARRAY'] and t.entry.d_val for t in module.get_section_by_name('.dynamic').iter_tags())
exports={s.name:s for s in module.get_section_by_name('.dynsym').iter_symbols()}
assert exports['yuy2_activate']['st_shndx']!='SHN_UNDEF'
results.append('producer_has_no_load_time_constructor_and_exports_lazy_activation')
needed=[t.needed for t in e.get_section_by_name('.dynamic').iter_tags() if t.entry.d_tag=='DT_NEEDED']
assert needed[:-1]==[t.needed for t in old.get_section_by_name('.dynamic').iter_tags() if t.entry.d_tag=='DT_NEEDED']
assert needed[-1]==patch.DEPENDENCY
results.append('original_dependencies_preserved_and_patch_dependency_added')
tags={t.entry.d_tag:t.entry.d_val for t in e.get_section_by_name('.dynamic').iter_tags()}
for tag,name in [('DT_STRTAB','.dynstr'),('DT_SYMTAB','.dynsym'),('DT_VERSYM','.gnu.version'),('DT_REL','.rel.dyn')]:
 assert tags[tag]==e.get_section_by_name(name)['sh_addr']
for sn in ['.dynstr','.dynsym','.gnu.version','.rel.dyn','.dynamic']:
 s=e.get_section_by_name(sn);assert any(p['p_type']=='PT_LOAD' and p['p_vaddr']<=s['sh_addr'] and s['sh_addr']+s['sh_size']<=p['p_vaddr']+p['p_filesz'] for p in e.iter_segments())
assert e.get_section_by_name('.gnu.hash').data()==old.get_section_by_name('.gnu.hash').data()
assert e.get_section_by_name('.rel.plt').data()==old.get_section_by_name('.rel.plt').data()
assert e.get_section_by_name('.dynsym').data()[:-16]==old.get_section_by_name('.dynsym').data()
assert e.get_section_by_name('.rel.dyn').data()[:-8]==old.get_section_by_name('.rel.dyn').data()
results.append('dynamic_tables_mapped_consistent_existing_symbol_and_relocation_indices_stable')
lo,hi=report['bss_file_range'];assert data[lo:hi]==b'\0'*(hi-lo)
assert e.get_section_by_name('.shstrtab').data()==old.get_section_by_name('.shstrtab').data()
results.append('old_bss_stays_zero_and_overlapping_section_names_are_preserved')
rel=list(e.get_section_by_name('.rel.dyn').iter_relocations())[-1]
assert rel['r_offset']==report['activation_got'] and rel['r_info_type']==21
assert e.get_section_by_name('.dynsym').get_symbol(rel['r_info_sym']).name=='yuy2_activate'
results.append('activation_pointer_is_resolved_by_dynamic_loader_not_fixed_address')
for base in [0x1000000,0xa61e000,0x1c000000]:
 for success in [False,True]:
  u=Uc(UC_ARCH_ARM,UC_MODE_THUMB);end=max(p['p_vaddr']+p['p_memsz'] for p in e.iter_segments() if p['p_type']=='PT_LOAD')
  u.mem_map(base,(end+4095)&~4095)
  for p in e.iter_segments():
   if p['p_type']=='PT_LOAD':u.mem_write(base+p['p_vaddr'],p.data())
  STACK=0x60008000;STOP=0x50000000;FUNC=0x40000000
  for p in [STACK-0x8000,STOP,FUNC]:u.mem_map(p,0x10000 if p==STACK-0x8000 else 4096)
  u.mem_write(base+report['activation_got'],struct.pack('<I',FUNC|1))
  u.reg_write(UC_ARM_REG_SP,STACK);u.reg_write(UC_ARM_REG_LR,STOP|1)
  regs=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7]
  values=[0x11110000+i for i in range(8)]
  for r,v in zip(regs,values):u.reg_write(r,v)
  calls=[]
  def hook(u,pc,size,user):
   if pc==FUNC:
    calls.append(pc);assert u.reg_read(UC_ARM_REG_SP)%8==0
    for r in regs[:4]:u.reg_write(r,0xdeadbeef)
    u.reg_write(UC_ARM_REG_R0,1 if success else 0);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,hook)
  target=base+patch.ENTRY+12 if success else STOP
  u.emu_start((base+patch.ENTRY)|1,target,count=200)
  assert calls==[FUNC] and u.reg_read(UC_ARM_REG_PC)==target
  if success:
   assert u.reg_read(UC_ARM_REG_R4)==values[0] and u.reg_read(UC_ARM_REG_R0)==4
   assert u.reg_read(UC_ARM_REG_SP)==STACK-24 and u.reg_read(UC_ARM_REG_R7)==STACK-24
   assert list(struct.unpack('<6I',bytes(u.mem_read(STACK-24,24))))==[values[3],values[4],values[5],values[6],values[7],STOP|1]
  else:
   assert u.reg_read(UC_ARM_REG_R0)==4 and u.reg_read(UC_ARM_REG_SP)==STACK
   assert [u.reg_read(r) for r in regs[1:]]==values[1:]
  results.append(f'pic_prepare_{base:x}_'+('success_original_prologue' if success else 'failure_returns_without_original'))
out={'passed':len(results),'cases':results,'hardware_services_mocked':True,'limitations':['ELF/ARM emulation does not replace target dynamic-loader and reboot tests']}
a.candidate.with_name('persistent-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
