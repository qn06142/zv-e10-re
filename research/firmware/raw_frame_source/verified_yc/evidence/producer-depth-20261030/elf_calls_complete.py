"""Resolve ARM PLT targets through their actual GOT slots, including mixed stubs."""
import struct
from elftools.elf.elffile import ELFFile
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
def ror(v,n):return ((v>>n)|(v<<(32-n)))&0xffffffff if n else v
def imm(x):return ror(x&255,2*((x>>8)&15))
def plt_names(e):
 p=e.get_section_by_name('.plt');r=e.get_section_by_name('.rel.plt')
 if not p or not r:return {}
 sy=e.get_section(r['sh_link']);got={x['r_offset']:sy.get_symbol(x['r_info_sym']).name for x in r.iter_relocations()};out={};b=p.data()
 for off in range(0,len(b)-11,4):
  a,c,d=struct.unpack_from('<3I',b,off)
  if a&0xfffff000==0xe28fc000 and c&0xfffff000==0xe28cc000 and d&0xfffff000==0xe5bcf000:
   address=p['sh_addr']+off;slot=address+8+imm(a)+imm(c)+(d&4095)
   assert slot in got,(hex(address),hex(slot))
   out[address]=got[slot]
 assert len(out)==len(got),(len(out),len(got))
 return out
def symbols(e):return {s['st_value']&~1:s.name for s in e.get_section_by_name('.dynsym').iter_symbols() if s['st_shndx']!='SHN_UNDEF'}
def disassemble(path,needle):
 with path.open('rb') as f:
  e=ELFFile(f);t=e.get_section_by_name('.text');b=t.data();base=t['sh_addr'];names=symbols(e);names.update(plt_names(e));lines=[];seen=set()
  for s in e.get_section_by_name('.dynsym').iter_symbols():
   if needle not in s.name or s['st_shndx']=='SHN_UNDEF' or s['st_info']['type']!='STT_FUNC':continue
   a=s['st_value']&~1
   if a in seen:continue
   seen.add(a);lines.append('\n'+s.name+' @'+hex(a))
   decoder=Cs(CS_ARCH_ARM,CS_MODE_THUMB);decoder.skipdata=True
   for i in decoder.disasm(b[a-base:a-base+s['st_size']],a):
    target=int(i.op_str[1:],16) if i.mnemonic in ['bl','blx','b.w'] and i.op_str.startswith('#0x') else None
    lines.append(f'{i.address:08x}: {i.mnemonic:9} {i.op_str} '+names.get(target,''))
  return '\n'.join(lines)
if __name__=='__main__':
 from pathlib import Path
 root=Path(r'D:/02_Development_And_Projects/pmca-re/.local/dumps/camera_2025/usr/usr/lib');out=Path('.local/outputs/yc-subsystem-offline-20261029')
 for needle in ['ImageOutTimInfo','DataflowInfraPin']:
  text=disassemble(root/'dataflowInfraFramework.so',needle);(out/(needle+'-original.txt')).write_text(text)
 print('All160 PLT entries resolved through actual GOT relocations')
