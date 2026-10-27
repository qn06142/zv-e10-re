from pathlib import Path
import struct,json,bisect,array
from elftools.elf.elffile import ELFFile
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
ROOT=Path(r'D:/02_Development_And_Projects/pmca-re/dumps/camera_2025/usr/usr/lib');OUT=Path('outputs/yc-vga-test')
name='libObj.so'
with (ROOT/name).open('rb') as f:
 e=ELFFile(f);segments=[(s['p_vaddr'],s.data()) for s in e.iter_segments() if s['p_type']=='PT_LOAD']
 def rd(a,n):
  for base,b in segments:
   if base<=a and a+n<=base+len(b):return b[a-base:a-base+n]
  return b''
 def string(a):
  b=rd(a,120).split(b'\0')[0]
  return b.decode('ascii') if len(b)>=4 and all(x in [9,10,13] or 32<=x<127 for x in b) else ''
 def prel(word,at):return (at+((word&0x7fffffff)-(0x80000000 if word&0x40000000 else 0)))&0xffffffff
 x=e.get_section_by_name('.ARM.exidx');entries=[]
 for off in range(0,x['sh_size'],8):entries.append(prel(struct.unpack_from('<I',x.data(),off)[0],x['sh_addr']+off)&~1)
 print('unwind function ranges',len(entries));assert entries==sorted(entries)
 # Reconstruct all known PLT import targets.
 relnames={}
 for sec in e.iter_sections():
  if sec.name not in ['.rel.plt','.rel.dyn']:continue
  sy=e.get_section(sec['sh_link'])
  for r in sec.iter_relocations():relnames[r['r_offset']]=sy.get_symbol(r['r_info_sym']).name
 def imm(w):
  n=w&255;r=((w>>8)&15)*2;return ((n>>r)|(n<<(32-r)))&0xffffffff if r else n
 plt=e.get_section_by_name('.plt');b=plt.data();base=plt['sh_addr'];targets={}
 for i in range(0,len(b)-11,4):
  w0,w1,w2=struct.unpack_from('<III',b,i)
  if w0&0xfffff000==0xe28fc000 and w1&0xfffff000==0xe28cc000 and w2&0xfffff000==0xe5bcf000:
   got=base+i+8+imm(w0)+imm(w1)+(w2&4095)
   if got in relnames:
    targets[base+i]=relnames[got]
    if i>=4 and b[i-4:i]==bytes.fromhex('7847c046'):targets[base+i-4]=relnames[got]

 wanted_targets={0x18a58c:'MLM_resize_helper',0x19fc88:'Artfilter_resize_helper'}
 print('targets',wanted_targets)
 hits=[];wanted=set()
 for sec in e.iter_sections():
  if not sec['sh_flags']&4:continue
  blob=sec.data();h=array.array('H',blob[:len(blob)//2*2]);base=sec['sh_addr']
  for ix in range(len(h)-1):
   a,c=h[ix],h[ix+1]
   if a&0xf800!=0xf000 or c&0xc000!=0xc000:continue
   s=(a>>10)&1;i1=1^(((c>>13)&1)^s);i2=1^(((c>>11)&1)^s)
   value=(s<<24)|(i1<<23)|(i2<<22)|((a&1023)<<12)|((c&2047)<<1)
   if s:value-=1<<25
   at=base+ix*2;dest=((at+4+value)&0xffffffff) if c&0x1000 else (((at+4)&~3)+value)&0xffffffff
   if dest not in wanted_targets:continue
   idx=bisect.bisect_right(entries,at)-1;wanted.add(idx)
   hits.append({'at':hex(at),'target':wanted_targets[dest],'function':hex(entries[idx])})
 print(json.dumps(hits,indent=2));(OUT/'libObj-resize-parent-calls.json').write_text(json.dumps(hits,indent=2))
 decoder=Cs(CS_ARCH_ARM,CS_MODE_THUMB);reports=[];texts=[]
 for index in sorted(wanted):
  start,end=entries[index:index+2]
  if end-start>20000:continue
  instructions=list(decoder.disasm_lite(rd(start,end-start),start));literals={};references=[];callsout=[];lines=[]
  for a,sz,mn,op in instructions:
   note=''
   if mn.startswith('ldr') and ', [pc, #' in op and op.endswith(']'):
    reg,disp=op.split(', [pc, #');at=((a+4)&~3)+int(disp[:-1],0);data=rd(at,4)
    if len(data)==4:literals[reg]=struct.unpack('<I',data)[0]
   if mn=='add' and op.endswith(', pc'):
    reg=op.split(',')[0]
    if reg in literals:
     adr=(literals[reg]+a+4)&0xffffffff;t=string(adr)
     if t:note=repr(t);references.append({'at':hex(a),'string':t})
   if mn in ['bl','blx'] and op.startswith('#'):
    dest=int(op[1:],0);note=targets.get(dest,'');callsout.append({'at':hex(a),'target':note or hex(dest)})
   lines.append(f'{a:08x}: {mn:8} {op} {note}')
  reports.append({'start':hex(start),'end':hex(end),'strings':references,'calls':callsout});texts.append('\nFUNCTION '+hex(start)+'..'+hex(end)+'\n'+'\n'.join(lines))
 (OUT/'libObj-resize-parent-functions.json').write_text(json.dumps(reports,indent=2));(OUT/'libObj-resize-parent-functions.txt').write_text('\n'.join(texts))
 for r in reports:print(r['start'],r['end'],[x['string'] for x in r['strings']][:4])
