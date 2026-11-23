"""Resolve direct Thumb BL callers in saved ELF files; offline only."""
from pathlib import Path
from elftools.elf.elffile import ELFFile
from capstone import *
import struct,json,argparse
ap=argparse.ArgumentParser();ap.add_argument('library');ap.add_argument('target',type=lambda x:int(x,0));ap.add_argument('--output',required=True);a=ap.parse_args()
p=Path('D:/02_Development_And_Projects/pmca-re/.local/dumps/camera_2025/usr/usr/lib')/a.library
with p.open('rb') as f:
 e=ELFFile(f);t=e.get_section_by_name('.text');b=t.data();base=t['sh_addr'];sy=[(s['st_value']&~1,s['st_size'],s.name) for s in e.get_section_by_name('.dynsym').iter_symbols() if s['st_shndx']!='SHN_UNDEF']
 rows=[];contexts=[]
 for off in range(0,len(b)-4,2):
  h1,h2=struct.unpack_from('<HH',b,off)
  if h1&0xf800!=0xf000 or h2&0xd000!=0xd000:continue
  S=h1>>10&1;delta=(S<<24)|(((~((h2>>13&1)^S))&1)<<23)|(((~((h2>>11&1)^S))&1)<<22)|((h1&1023)<<12)|((h2&2047)<<1)
  if S:delta-=1<<25
  pc=base+off
  if (pc+4+delta)&0xffffffff!=a.target:continue
  owners=[n for start,size,n in sy if start<=pc<start+size];rows.append({'caller':hex(pc),'owners':owners})
  contexts.append('\n'.join(f'{i.address:08x}: {i.mnemonic:9} {i.op_str}' for i in Cs(CS_ARCH_ARM,CS_MODE_THUMB).disasm(b[max(0,off-64):off+20],max(base,pc-64))))
 out=Path(a.output);out.with_suffix('.json').write_text(json.dumps(rows,indent=2));out.with_suffix('.txt').write_text('\n\n'.join(contexts));print(json.dumps(rows,indent=2))
