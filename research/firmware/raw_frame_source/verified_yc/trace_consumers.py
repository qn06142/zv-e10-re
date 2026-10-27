from pathlib import Path
import struct,json,array
from elftools.elf.elffile import ELFFile
from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM,CS_MODE_THUMB
ROOT=Path(r'D:/02_Development_And_Projects/pmca-re/dumps/camera_2025/usr/usr/lib');OUT=Path('outputs/yc-source-re-20261025');OUT.mkdir(exist_ok=True)
def imm(w):
 n=w&255;r=((w>>8)&15)*2;return ((n>>r)|(n<<(32-r)))&0xffffffff if r else n
for filename in ['libBizFw.so','libObj.so']:
 with (ROOT/filename).open('rb') as f:
  e=ELFFile(f);plt=e.get_section_by_name('.plt');data=plt.data();base=plt['sh_addr'];names={}
  for sec in e.iter_sections():
   if sec.name not in ['.rel.plt','.rel.dyn']:continue
   sy=e.get_section(sec['sh_link'])
   for r in sec.iter_relocations():names[r['r_offset']]=sy.get_symbol(r['r_info_sym']).name
  targets={}
  for i in range(0,len(data)-12+1,4):
   w0,w1,w2=struct.unpack_from('<III',data,i)
   if w0&0xfffff000==0xe28fc000 and w1&0xfffff000==0xe28cc000 and w2&0xfffff000==0xe5bcf000:
    got=base+i+8+imm(w0)+imm(w1)+(w2&4095)
    if got in names:
     targets[base+i]=names[got]
     if i>=4 and data[i-4:i]==bytes.fromhex('7847c046'):targets[base+i-4]=names[got]
  selected={a:n for a,n in targets.items() if any(k in n for k in ['StdData_YCC1','GetEntry_ImageSizeInfo','GetEntry_YcStateInfo','ImageSizeInfo11GetData_All','DmmCh4open','DmmCh5close'])}
  funcs={}
  for sn in ['.dynsym','.symtab']:
   sec=e.get_section_by_name(sn)
   if sec:
    for s in sec.iter_symbols():
     if s['st_info']['type']=='STT_FUNC' and s['st_size'] and s['st_shndx']!='SHN_UNDEF':funcs[(s['st_value']&~1,s['st_size'])]=s
  matches=[];details=[]
  for (address,size),s in sorted(funcs.items()):
   if not isinstance(s['st_shndx'],int):continue
   section=e.get_section(s['st_shndx']);start=address-section['sh_addr'];blob=section.data()[start:start+size]
   instructions=list(Cs(CS_ARCH_ARM,CS_MODE_THUMB if s['st_value']&1 else CS_MODE_ARM).disasm_lite(blob,address))
   hits=[]
   for index,(a,sz,mn,op) in enumerate(instructions):
    if mn not in ['bl','blx','b','b.w'] or not op.startswith('#'):continue
    try:dest=int(op[1:],0)
    except ValueError:continue
    if dest in selected:hits.append((index,a,selected[dest],dest))
   if hits:
    matches.append({'function':s.name,'address':hex(address),'size':size,'calls':[{'at':hex(a),'target':n,'plt':hex(d)} for _,a,n,d in hits]})
    details.append(f'\nFUNCTION {s.name} {address:08x} size{size}')
    for a,sz,mn,op in instructions:
     name=targets.get(int(op[1:],0),'') if mn in ['bl','blx','b','b.w'] and op.startswith('#0x') else ''
     details.append(f'{a:08x}: {mn:8} {op} {name}')
  # Include stripped local consumers: dynamic symbols cover only part of libObj.
  raw=[];text=e.get_section_by_name('.text');blob=text.data();half=array.array('H',blob);decoder=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
  for index in range(len(half)-1):
   first,second=half[index],half[index+1]
   if first&0xf800!=0xf000 or second&0xc000!=0xc000:continue
   address=text['sh_addr']+index*2
   ins=list(decoder.disasm_lite(blob[index*2:index*2+4],address))
   if len(ins)!=1 or ins[0][2] not in ['bl','blx']:continue
   try:dest=int(ins[0][3].removeprefix('#'),0)
   except ValueError:continue
   if dest not in selected:continue
   raw.append({'at':hex(address),'target':selected[dest],'plt':hex(dest)})
   details.append(f'\nRAW CALL {address:x} {selected[dest]} (local function boundaries not yet recovered)')
   begin=max(0,index*2-48)
   for a,sz,mn,op in decoder.disasm_lite(blob[begin:index*2+28],text['sh_addr']+begin):details.append(f'{a:08x}: {mn:8} {op}')
  (OUT/(filename+'.yc-raw-xrefs.json')).write_text(json.dumps(raw,indent=2));print(filename,'raw candidate callsites',len(raw))
  (OUT/(filename+'.yc-callers.json')).write_text(json.dumps(matches,indent=2));(OUT/(filename+'.yc-callers.txt')).write_text('\n'.join(details));print(filename,len(targets),'PLT targets',len(matches),'YC consumer functions')
