from pathlib import Path
from elftools.elf.elffile import ELFFile
from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM
root=Path('D:/02_Development_And_Projects/pmca-re/.local/dumps/camera_2025/usr/usr')
out=Path('.local/outputs/yc-frame-contract-20261029')
with (root/'.local/kmod/usbg_video.ko').open('rb') as f:
 e=ELFFile(f);sy=e.get_section_by_name('.symtab');t=e.get_section_by_name('.text');b=t.data();rels={}
 for r in e.get_section_by_name('.rel.text').iter_relocations():
  s=sy.get_symbol(r['r_info_sym']);rels[r['r_offset']]=s.name+' + '+hex(s['st_value'])
 lines=[]
 for s in sy.iter_symbols():
  if s['st_info']['type']!='STT_FUNC' or s['st_shndx']!='SHN_UNDEF' and not s['st_size']:continue
  if s['st_shndx']=='SHN_UNDEF':continue
  a=s['st_value'];lines.append('\n'+s.name+' '+hex(a)+' size '+hex(s['st_size']))
  for i in Cs(CS_ARCH_ARM,CS_MODE_ARM).disasm(b[a:a+s['st_size']],a):
   lines.append(f'{i.address:08x}: {i.mnemonic:9} {i.op_str} '+rels.get(i.address,''))
 (out/'usb-kernel-original.txt').write_text('\n'.join(lines))
 for name,start,end in [('worker',0x8c8,0x10f0),('submit',0xd00,0x10f0)]:
  q=[];cs=Cs(CS_ARCH_ARM,CS_MODE_ARM);cs.skipdata=True
  for i in cs.disasm(b[start:end],start):
   q.append(f'{i.address:08x}: {i.mnemonic:9} {i.op_str} '+rels.get(i.address,''))
  (out/('usb-'+name+'-original.txt')).write_text('\n'.join(q))
 print('\n'.join(l for l in lines if not l[:1].isdigit()))

