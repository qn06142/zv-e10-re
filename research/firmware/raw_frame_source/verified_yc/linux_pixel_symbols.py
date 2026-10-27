from pathlib import Path
from elftools.elf.elffile import ELFFile
import re,json
root=Path(r'D:/02_Development_And_Projects/pmca-re/dumps/camera_2025/usr/usr/lib');hits=[]
for p in root.glob('*.so'):
 try:
  with p.open('rb') as f:
   e=ELFFile(f);sec=e.get_section_by_name('.dynsym')
   if not sec:continue
   for s in sec.iter_symbols():
    if s['st_shndx']=='SHN_UNDEF':continue
    n=s.name
    if re.search(r'(yuv|ycbcr|yuyv|yuy2|nv12|nv16)',n,re.I) or ('Yc' in n and re.search(r'(convert|copy|pixel|image|addr|frame|buffer|live|preview)',n,re.I)):
     hits.append(dict(file=p.name,address=hex(s['st_value']),size=s['st_size'],name=n))
 except Exception:pass
Path('outputs/yc-source-re-20261025/linux-pixel-symbols.json').write_text(json.dumps(hits,indent=2))
for x in hits:print(x['file'],x['address'],x['name'])
