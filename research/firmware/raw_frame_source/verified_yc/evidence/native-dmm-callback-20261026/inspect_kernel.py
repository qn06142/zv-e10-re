from pathlib import Path
from elftools.elf.elffile import ELFFile
from capstone import *
p=Path(r'D:/02_Development_And_Projects/pmca-re/dumps/camera_2025/usr/usr/kmod/dmm.ko');lines=[]
with p.open('rb') as f:
 e=ELFFile(f);sy=e.get_section_by_name('.symtab');rels={}
 for sec in e.iter_sections():
  if sec.name=='.rel.text':
   symbols=e.get_section(sec['sh_link'])
   for r in sec.iter_relocations():rels[r['r_offset']]=symbols.get_symbol(r['r_info_sym']).name
 for s in sy.iter_symbols():
  if s.name not in ['dmm_unit_ctrl_Free','dmm_unit_ctrl_Close','dmm_ctrl_OpenUnitHdlr','dmm_ctrl_CloseUnitHdlr','dmm_unit_ctrl_Share','dmm_ctrl_AllocUnitShareHdlr']:continue
  sec=e.get_section(s['st_shndx']);start=s['st_value'];lines.append('\n'+s.name)
  for i in Cs(CS_ARCH_ARM,CS_MODE_ARM).disasm(sec.data()[start:start+s['st_size']],start):lines.append(f'{i.address:08x} {i.mnemonic:8} {i.op_str} {rels.get(i.address,"")}')
Path('outputs/native-dmm-callback/kernel-open-close-free.txt').write_text('\n'.join(lines));print('\n'.join(lines))
