from pathlib import Path
import io,struct,json,hashlib,subprocess
from elftools.elf.elffile import ELFFile
W=Path('.local/work/hd-v42');O=Path('.local/outputs/hd-v42');O.mkdir(exist_ok=True)
subprocess.run(['C:/msys64/ucrt64/bin/arm-none-eabi-gcc.exe','-mcpu=cortex-a5','-marm','-c',str(W/'kernel_chunk.S'),'-o',str(O/'kernel_chunk.o')],check=True)
src=Path('.local/outputs/vga-v40/usbg_video.ko').read_bytes();assert hashlib.md5(src).hexdigest()=='388799d95bbb524ca581c66b077b6dc2'
e=ELFFile(io.BytesIO(src));a=ELFFile(io.BytesIO((O/'kernel_chunk.o').read_bytes()));out=bytearray(src);shoff=e['e_shoff'];heads=[list(struct.unpack_from('<10I',src,shoff+40*i)) for i in range(e['e_shnum'])];ix={s.name:i for i,s in enumerate(e.iter_sections())};newi=len(heads)
def append(data,alignment=4):
 pos=(len(out)+alignment-1)&~(alignment-1);out.extend(bytes(pos-len(out)));out.extend(data);return pos
def replace(i,data):heads[i][4]=append(data);heads[i][5]=len(data)
sy=e.get_section_by_name('.symtab');symdata=bytearray(sy.data());st=sy['sh_link'];strings=bytearray(e.get_section(st).data());indices={}
def symbol(name,value,section,kind,size=0):
 idx=len(symdata)//16;at=len(strings);strings.extend(name.encode()+b'\0');symdata.extend(struct.pack('<IIIBBH',at,value,size,0x10|kind,0,section));indices[name]=idx;return idx
for s in a.get_section_by_name('.symtab').iter_symbols():
 if s.name.startswith('__yc42_') and s['st_shndx']!='SHN_UNDEF':symbol(s.name,s['st_value'],newi,2,s['st_size'])
for n,off in [('__yc42_ret_extract',0xe78),('__yc42_ret_fid',0xee0),('__yc42_ret_eof',0xf48)]:symbol(n,off,ix['.text'],0)
text=bytearray(e.get_section_by_name('.text').data());rel=bytearray(e.get_section_by_name('.rel.text').data());existing={r['r_offset'] for r in e.get_section_by_name('.rel.text').iter_relocations()};edits=[]
for off,expected,n in [(0xe74,0xe51b702c,'__yc42_extract_size'),(0xed0,0xe3530001,'__yc42_fid'),(0xf44,0xe2488072,'__yc42_eof')]:
 assert struct.unpack_from('<I',text,off)[0]==expected and off not in existing
 struct.pack_into('<I',text,off,0xeafffffe);rel.extend(struct.pack('<II',off,(indices[n]<<8)|29));edits.append({'offset':hex(off),'stub':n})
out[e.get_section_by_name('.text')['sh_offset']:e.get_section_by_name('.text')['sh_offset']+len(text)]=text
replace(ix['.symtab'],symdata);replace(st,strings);replace(ix['.rel.text'],rel)
shstr=bytearray(e.get_section(e['e_shstrndx']).data());name1=len(shstr);shstr.extend(b'.text.yc42_chunk\0');name2=len(shstr);shstr.extend(b'.rel.text.yc42_chunk\0');replace(e['e_shstrndx'],shstr)
blob=a.get_section_by_name('.text.yc42_chunk').data();newrel=bytearray();asy=a.get_section_by_name('.symtab')
for r in a.get_section_by_name('.rel.text.yc42_chunk').iter_relocations():
 n=asy.get_symbol(r['r_info_sym']).name;assert r['r_info_type']==29 and n in indices;newrel.extend(struct.pack('<II',r['r_offset'],(indices[n]<<8)|29))
heads.append([name1,1,6,0,append(blob),len(blob),0,0,4,0]);heads.append([name2,9,0x40,0,append(newrel),len(newrel),ix['.symtab'],newi,4,8])
mod=e.get_section_by_name('.modinfo');data=mod.data();old=b'version=yc37_fence\0';new=b'version=yc42_chunk\0';assert old in data and len(old)==len(new);pos=mod['sh_offset']+data.index(old);out[pos:pos+len(new)]=new
newsh=append(b''.join(struct.pack('<10I',*h) for h in heads));struct.pack_into('<I',out,32,newsh);struct.pack_into('<H',out,48,len(heads))
final=bytes(out);(O/'usbg_video.ko').write_bytes(final);r={'baseline_md5':hashlib.md5(src).hexdigest(),'md5':hashlib.md5(final).hexdigest(),'edits':edits,'preserves_yc37_fence':True,'new_imports':False,'chunk_tag':'0x20000000','fid_flag':'0x40000000','more_flag':'0x80000000'};(O/'kernel-build.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
