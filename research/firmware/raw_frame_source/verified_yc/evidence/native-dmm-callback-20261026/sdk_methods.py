from pathlib import Path
from elftools.elf.elffile import ELFFile
from capstone import *
p=Path(r'D:/02_Development_And_Projects/pmca-re/dumps/camera_2025/usr/usr/lib/libBizFw.so');lines=[]
with p.open('rb') as f:
 e=ELFFile(f);sy=e.get_section_by_name('.dynsym');t=e.get_section_by_name('.text');b=t.data();base=t['sh_addr'];d=Cs(CS_ARCH_ARM,CS_MODE_THUMB);d.skipdata=True
 for s in sy.iter_symbols():
  if s['st_shndx']=='SHN_UNDEF' or 'DmmCh' not in s.name or not any(x in s.name for x in ['shareE','4freeE','4openE','5closeE']):continue
  lines.append('\n'+s.name+' '+hex(s['st_value']))
  for i in d.disasm(b[(s['st_value']&~1)-base:(s['st_value']&~1)-base+s['st_size']],s['st_value']&~1):lines.append(f'{i.address:08x}: {i.mnemonic:8} {i.op_str}')
Path('outputs/native-dmm-callback/sdk-dmm-methods.txt').write_text('\n'.join(lines));print('\n'.join(lines[:175]))
