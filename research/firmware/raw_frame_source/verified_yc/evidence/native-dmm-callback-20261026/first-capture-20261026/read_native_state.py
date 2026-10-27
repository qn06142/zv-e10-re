from pathlib import Path
import json,re
from elftools.elf.elffile import ELFFile
O=Path('outputs/native-dmm-callback/deployment/live/first-capture-01');maps=[]
for line in (O/'maps.txt').read_text().splitlines():
 m=re.match(r'([0-9a-f]+)-([0-9a-f]+) (....) ([0-9a-f]+).*',line)
 if m:maps.append((int(m[1],16),int(m[2],16),m[3],line))
base=next(lo for lo,hi,perm,line in maps if '/usr/lib/yuy2_640_v27snap.so' in line and 'r-x' in perm)
with Path('outputs/native-dmm-callback/candidate/yuy2_640_v27snap.so').open('rb') as f:
 e=ELFFile(f);symbols={s.name:(s['st_value'],s['st_size']) for s in e.get_section_by_name('.symtab').iter_symbols() if s.name in ['live_source','frames','raw_errors','listing','backend','failed','initialized']}
lo=(base+min(v for v,n in symbols.values()))&~4095;hi=(base+max(v+n for v,n in symbols.values())+4095)&~4095
for page in range(lo,hi,4096):assert any(a<=page and page+4096<=b and 'r' in p for a,b,p,l in maps),(hex(page),'unmapped')
meta={'load_base':base,'read_start':lo,'read_bytes':hi-lo,'symbols':symbols,'read_only':True,'addresses_derived_from_this_session_maps':True};(O/'state-layout.json').write_text(json.dumps(meta,indent=2)+'\n')
D='/log/yuy2_640_v27snap';C=D+'/first-capture-01';cmd=f'P=$(/bin/busybox pidof im.elf); {D}/busybox dd if=/proc/$P/mem of={C}/module-state.bin bs=4096 skip={lo//4096} count={(hi-lo)//4096}'
job={'terminal_lines':[cmd,f'/bin/busybox md5sum {C}/module-state.bin'],'downloads':[[C+'/module-state.bin',str(O/'module-state.bin')]]}
Path('work/native-dmm-callback/live-jobs/025-read-callback-state.json').write_text(json.dumps(job,indent=2));print(meta)
