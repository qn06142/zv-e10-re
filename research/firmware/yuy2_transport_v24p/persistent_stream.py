"""Rebuild only ELF dynamic tables and add a position-independent prepare gate."""
from pathlib import Path
import argparse,hashlib,io,json,struct
from elftools.elf.elffile import ELFFile
from keystone import Ks,KS_ARCH_ARM,KS_MODE_THUMB

BASE_MD5='19461091c07aa6900829defb0060fcd6'
DEPENDENCY='yuy2_640_v24p.so'
SYMBOL='yuy2_activate'
CAVE=0x90c0;CAVE_SIZE=380;ENTRY=0x8d00
def align(v,a=4):return (v+a-1)&~(a-1)

def build(data):
 assert hashlib.md5(data).hexdigest()==BASE_MD5,'Unexpected streaming library baseline'
 e=ELFFile(io.BytesIO(data));assert e.elfclass==32 and e.little_endian
 assert e['e_machine']=='EM_ARM' and e['e_type']=='ET_DYN'
 out=bytearray(data);shoff=e['e_shoff'];phoff=e['e_phoff']
 sections={s.name:(i,s) for i,s in enumerate(e.iter_sections())}
 rw_index,rw=next((i,p) for i,p in enumerate(e.iter_segments()) if p['p_type']=='PT_LOAD' and p['p_flags']==6)
 delta=rw['p_vaddr']-rw['p_offset']
 # Extending PT_LOAD must not initialize old BSS with nonallocated ELF metadata.
 bss_lo=rw['p_offset']+rw['p_filesz'];bss_hi=rw['p_offset']+rw['p_memsz']
 for name,(index,s) in sections.items():
  if s['sh_type']=='SHT_NOBITS' or not s['sh_size']:continue
  lo=s['sh_offset'];hi=lo+s['sh_size']
  if lo<bss_hi and bss_lo<hi:
   assert not s['sh_flags']&2,'Allocated section unexpectedly overlaps old BSS'
   pos=align(len(out),max(1,s['sh_addralign']));out.extend(b'\0'*(pos-len(out)));out.extend(s.data())
   struct.pack_into('<I',out,shoff+index*40+16,pos)
 assert not (shoff<bss_hi and bss_lo<shoff+e['e_shnum']*40)
 out[bss_lo:bss_hi]=b'\0'*(bss_hi-bss_lo)
 def append(blob,boundary=4):
  pos=align(len(out),boundary);out.extend(b'\0'*(pos-len(out)));out.extend(blob)
  return pos,pos+delta
 def replace_section(name,blob,boundary=4):
  index,s=sections[name];pos,va=append(blob,boundary)
  struct.pack_into('<III',out,shoff+index*40+12,va,pos,len(blob))
  return va
 old_strings=e.get_section_by_name('.dynstr').data();sym=e.get_section_by_name('.dynsym')
 needed_offset=len(old_strings);symbol_offset=needed_offset+len(DEPENDENCY)+1
 strings=old_strings+DEPENDENCY.encode()+b'\0'+SYMBOL.encode()+b'\0'
 string_va=replace_section('.dynstr',strings)
 old_syms=sym.data();index=len(old_syms)//16
 new_sym=struct.pack('<IIIBBH',symbol_offset,0,0,0x12,0,0)
 sym_va=replace_section('.dynsym',old_syms+new_sym)
 version_va=replace_section('.gnu.version',e.get_section_by_name('.gnu.version').data()+struct.pack('<H',1),2)
 slot_offset,slot_va=append(b'\0'*4)
 old_rels=e.get_section_by_name('.rel.dyn').data()
 rels=old_rels+struct.pack('<II',slot_va,(index<<8)|21)
 rel_va=replace_section('.rel.dyn',rels)
 # Existing symbol indices, hash tables and all old relocation targets stay stable.
 tags=[]
 overrides={5:string_va,6:sym_va,10:len(strings),17:rel_va,18:len(rels),0x6ffffff0:version_va}
 for tag in e.get_section_by_name('.dynamic').iter_tags():
  value=tag.entry.d_val
  # Read the numeric tag from original bytes; pyelftools gives symbolic names.
  tag_number=struct.unpack_from('<I',e.get_section_by_name('.dynamic').data(),len(tags)*8)[0]
  if tag_number==0:break
  tags.append((tag_number,overrides.get(tag_number,value)))
 tags.extend([(1,needed_offset),(0,0)])
 dyn_blob=b''.join(struct.pack('<II',a,b) for a,b in tags)
 dyn_va=replace_section('.dynamic',dyn_blob)
 dyn_index=next(i for i,p in enumerate(e.iter_segments()) if p['p_type']=='PT_DYNAMIC')
 struct.pack_into('<IIIIII',out,phoff+dyn_index*32+4,dyn_va-delta,dyn_va,dyn_va,len(dyn_blob),len(dyn_blob),6)
 # Keep flags/alignment and all existing mappings; extend only the final RW load.
 size=len(out)-rw['p_offset']
 struct.pack_into('<II',out,phoff+rw_index*32+16,size,size)
 assert out[ENTRY:ENTRY+12]==bytes.fromhex('f8b50021044600af04200a46')
 asm=f'''
entry:
 push {{r0,r1,r2,r3,r4,r5,r6,lr}}
 adr.w r2,entry
 ldr r3,slot_delta
 add r3,r2
 ldr r3,[r3]
 blx r3
 cmp r0,#1
 bne failed
 pop.w {{r0,r1,r2,r3,r4,r5,r6,lr}}
 push {{r3,r4,r5,r6,r7,lr}}
 movs r1,#0
 mov r4,r0
 add r7,sp,#0
 movs r0,#4
 mov r2,r1
 b.w {ENTRY+12:#x}
failed:
 pop.w {{r0,r1,r2,r3,r4,r5,r6,lr}}
 movs r0,#4
 bx lr
 .align 2
slot_delta: .word {slot_va-CAVE}
'''
 code=bytes(Ks(KS_ARCH_ARM,KS_MODE_THUMB).asm(asm,addr=CAVE)[0]);assert len(code)<=CAVE_SIZE
 code+=b'\x00\xbf'*((CAVE_SIZE-len(code))//2)
 assert len(code)==CAVE_SIZE
 out[CAVE:CAVE+CAVE_SIZE]=code
 branch=bytes(Ks(KS_ARCH_ARM,KS_MODE_THUMB).asm(f'b.w {CAVE:#x}',addr=ENTRY)[0])
 out[ENTRY:ENTRY+12]=branch+b'\x00\xbf'*4
 report={'dependency':DEPENDENCY,'activation_symbol':SYMBOL,'activation_symbol_index':index,
         'activation_got':slot_va,'entry':ENTRY,'cave':CAVE,'bss_file_range':[bss_lo,bss_hi],
         'baseline_md5':BASE_MD5,'md5':hashlib.md5(out).hexdigest(),'sha256':hashlib.sha256(out).hexdigest(),
         'bytes':len(out),'address_independent':True,'activation':'normal video prepare only; no patch constructor'}
 return bytes(out),report

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--input',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 assert not a.output.exists(),'Preserve existing generated evidence'
 result,report=build(a.input.read_bytes());a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(result)
 a.output.with_suffix('.persistent.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
