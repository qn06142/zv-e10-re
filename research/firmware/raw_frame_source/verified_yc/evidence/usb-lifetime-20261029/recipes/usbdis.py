"""Disassemble usbg_video.ko (original + candidate) with relocation names. Offline only."""
import io,sys,json,hashlib
from pathlib import Path
from elftools.elf.elffile import ELFFile
from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM
ORIG=Path('D:/02_Development_And_Projects/pmca-re/.local/dumps/camera_2025/usr/usr/kmod/usbg_video.ko')
CAND=Path('C:/Users/qn061/Documents/Codex/2026-10-22/chec/outputs/yuy2-640-v23/deployment/camera-after-tests/usbg_video.ko')
def load(p):
    d=p.read_bytes();e=ELFFile(io.BytesIO(d));sy=e.get_section_by_name('.symtab');t=e.get_section_by_name('.text')
    rels={}
    for r in e.get_section_by_name('.rel.text').iter_relocations():
        s=sy.get_symbol(r['r_info_sym']);rels[r['r_offset']]=(s.name,s['st_value'],r['r_info_type'])
    funcs=sorted([(s['st_value'],s['st_size'],s.name) for s in sy.iter_symbols() if s['st_info']['type']=='STT_FUNC' and s['st_shndx']!='SHN_UNDEF'])
    return d,t.data(),rels,funcs
def dis(code,rels,a,b):
    cs=Cs(CS_ARCH_ARM,CS_MODE_ARM);cs.skipdata=True;out=[]
    for i in cs.disasm(code[a:b],a):
        r=rels.get(i.address);out.append(f'{i.address:05x}: {i.mnemonic:8} {i.op_str}'+(f'   ; reloc {r[0]}+{r[1]:#x}' if r else ''))
    return out
if __name__=='__main__':
    out=Path(sys.argv[1])
    for tag,p in (('orig',ORIG),('cand',CAND)):
        d,code,rels,funcs=load(p)
        print(tag,hashlib.md5(d).hexdigest(),len(code))
        L=[]
        for a,s,n in funcs:
            L.append(f'\n== {n} {a:#x} size {s:#x}');L+=dis(code,rels,a,a+s)
        (out/f'usb-{tag}-full.txt').write_text('\n'.join(L))
        print([(hex(a),hex(s),n) for a,s,n in funcs])
