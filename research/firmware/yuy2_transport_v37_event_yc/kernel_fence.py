"""Offline guarded ET_REL repair: preserve source DMA failure status and unlock."""
from pathlib import Path
import struct,io,hashlib,json
from elftools.elf.elffile import ELFFile
BASELINE='c1cad400372e26eca729e4b9bc47a237'
def build(data):
 assert hashlib.md5(data).hexdigest()==BASELINE
 e=ELFFile(io.BytesIO(data));assert e['e_type']=='ET_REL' and e['e_machine']=='EM_ARM'
 shoff=e['e_shoff'];heads=[list(struct.unpack_from('<10I',data,shoff+40*i)) for i in range(e['e_shnum'])];names={s.name:i for i,s in enumerate(e.iter_sections())}
 text=e.get_section_by_name('.text').data();out=bytearray(data);patch=bytearray(text)
 sy=e.get_section_by_name('.symtab');si=names['.symtab'];ti=names['.text'];ri=names['.rel.text'];sti=sy['sh_link'];newi=len(heads)
 origsec=next(i for i,s in enumerate(sy.iter_symbols()) if s['st_info']['type']=='STT_SECTION' and s['st_shndx']==ti)
 def append(blob,alignment=4):
  pos=(len(out)+alignment-1)&~(alignment-1);out.extend(bytes(pos-len(out)));out.extend(blob);return pos
 def replace(index,blob):heads[index][4]=append(blob);heads[index][5]=len(blob)
 def badd(target):return 0xea000000|(((target-8)>>2)&0xffffff)
 # Relocated branches use an ARM REL24 addend, not a guessed loaded address.
 fence=struct.pack('<10I',0xe3e05004,badd(0x10b4),0xe3550000,0x1a000003,0xe287400c,badd(0x1050),0xe3e0500f,badd(0x10b4),0xe3e0506d,badd(0x10b4))
 symdata=bytearray(sy.data());strings=bytearray(e.get_section(sti).data());newsyms={}
 for n,off in [('__yc37_dma_start_failed',0),('__yc37_dma_waited',8),('__yc37_staging_busy',24)]:
  idx=len(symdata)//16;at=len(strings);strings.extend(n.encode()+b'\0');symdata.extend(struct.pack('<IIIBBH',at,off,0,0x12,0,newi));newsyms[n]=idx
 rel=bytearray(e.get_section_by_name('.rel.text').data());existing={r['r_offset'] for r in e.get_section_by_name('.rel.text').iter_relocations()}
 sites=[(0xf84,'__yc37_dma_start_failed',0xb,0xba000031),(0xf10,'__yc37_staging_busy',1,0x1a00006d),(0x104c,'__yc37_dma_waited',0xe,0xe287400c)]
 edits=[]
 for off,n,cond,expected in sites:
  actual=struct.unpack_from('<I',text,off)[0];assert actual==expected,(hex(off),hex(actual),hex(expected));assert off not in existing
  struct.pack_into('<I',patch,off,(cond<<28)|0x0afffffe);rel.extend(struct.pack('<II',off,(newsyms[n]<<8)|29));edits.append(dict(offset=hex(off),before=hex(actual),change=n))
 assert struct.unpack_from('<I',text,0x10cc)[0]==0xe3a00000
 struct.pack_into('<I',patch,0x10cc,0xe1a00005);edits.append(dict(offset='0x10cc',before='mov r0,#0',change='mov r0,r5: preserve DMA status'))
 # Replace code bytes in place; move metadata sections without changing indices.
 oldtext=e.get_section_by_name('.text');out[oldtext['sh_offset']:oldtext['sh_offset']+len(patch)]=patch
 replace(si,bytes(symdata));replace(sti,bytes(strings));replace(ri,bytes(rel))
 shstr=bytearray(e.get_section(e['e_shstrndx']).data());textname=len(shstr);shstr.extend(b'.text.yc37_fence\0');relname=len(shstr);shstr.extend(b'.rel.text.yc37_fence\0');replace(e['e_shstrndx'],bytes(shstr))
 heads.append([textname,1,6,0,append(fence),len(fence),0,0,4,0])
 newrel=b''.join(struct.pack('<II',off,(origsec<<8)|29) for off in [4,20,28,36])
 heads.append([relname,9,0x40,0,append(newrel),len(newrel),si,newi,4,8])
 info=e.get_section_by_name('.modinfo');old=b'version=yuy2_640_v23\0';new=b'version=yc37_fence\0';assert old in info.data()
 at=info['sh_offset']+info.data().index(old);out[at:at+len(old)]=new.ljust(len(old),b'\0')
 newshoff=append(b''.join(struct.pack('<10I',*h) for h in heads));struct.pack_into('<I',out,32,newshoff);struct.pack_into('<H',out,48,len(heads))
 final=bytes(out);check=ELFFile(io.BytesIO(final));assert check.get_section_by_name('.text.yc37_fence').data()==fence
 assert check.get_section_by_name('__param').data()==e.get_section_by_name('__param').data()
 return final,dict(camera_access=False,baseline_md5=BASELINE,output_md5=hashlib.md5(final).hexdigest(),output_sha256=hashlib.sha256(final).hexdigest(),edits=edits,added_sections=['.text.yc37_fence','.rel.text.yc37_fence'],new_imports=False,behavior=['DMA-start error returns -5 without marking slot ready','DMA timeout returns -110 without marking slot ready','busy double-staging path unlocks and returns -16','normal DMA completion returns zero'],limitations=['Target kernel module loading and hardware DMA still need validation.'])
if __name__=='__main__':
 src=Path('.local/outputs/yuy2-640-v24p/candidate/usbg_video.ko');O=Path('.local/outputs/vga-v37');O.mkdir(exist_ok=True);b,r=build(src.read_bytes());(O/'usbg_video.ko').write_bytes(b);(O/'kernel-fence.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
