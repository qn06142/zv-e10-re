from pathlib import Path
from elftools.elf.elffile import ELFFile
from capstone import *
p=Path(r'D:/02_Development_And_Projects/pmca-re/dumps/camera_2025/usr/usr/kmod/dmm.ko')
with p.open('rb') as f:
 e=ELFFile(f);b=e.get_section_by_name('.text').data();names={};sec=e.get_section_by_name('.rel.text');sy=e.get_section(sec['sh_link'])
 for r in sec.iter_relocations():names[r['r_offset']]=sy.get_symbol(r['r_info_sym']).name
 for start,end in [(0x5804,0x58dc),(0x5294,0x5310)]:
  for i in Cs(CS_ARCH_ARM,CS_MODE_ARM).disasm(b[start:end],start):print(hex(i.address),i.mnemonic,i.op_str,names.get(i.address,''))
