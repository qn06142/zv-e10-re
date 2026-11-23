"""Resolve literal-pool loads (ldr rX,[pc,#imm]) to section+addend for chosen ranges. Offline static only."""
import io,sys,json,struct
sys.path.insert(0,str(__import__('pathlib').Path(__file__).parent))
import usbdis as u
from elftools.elf.elffile import ELFFile
from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM
from capstone.arm import ARM_OP_MEM,ARM_REG_PC
def lits(path):
    d=path.read_bytes();e=ELFFile(io.BytesIO(d));sy=e.get_section_by_name('.symtab');t=e.get_section_by_name('.text');code=t.data()
    secs={i:s.name for i,s in enumerate(e.iter_sections())}
    rel={}
    for r in e.get_section_by_name('.rel.text').iter_relocations():
        s=sy.get_symbol(r['r_info_sym']);rel[r['r_offset']]=(s.name or secs.get(s['st_shndx'],'?'),)
    return code,rel,secs
def resolve(code,rel,a,b):
    cs=Cs(CS_ARCH_ARM,CS_MODE_ARM);cs.detail=True;cs.skipdata=True;out=[]
    for i in cs.disasm(code[a:b],a):
        if i.mnemonic=='ldr' and len(i.operands)==2 and i.operands[1].type==ARM_OP_MEM and i.operands[1].mem.base==ARM_REG_PC:
            la=i.address+8+i.operands[1].mem.disp
            if la+4<=len(code):
                w=struct.unpack_from('<I',code,la)[0];r=rel.get(la)
                out.append(dict(at=hex(i.address),literal_at=hex(la),section_or_symbol=(r[0] if r else 'absolute'),addend=hex(w)))
    return out
RANGES={'uvc_transfer_dmac_cb':(0x6a0,0x6ec),'core_cb_stop':(0x744,0x8c8),'submit_0xd00_0x10f0':(0xd00,0x10f0),
 'core_open':(0x1ac8,0x1cac),'core_release':(0x1cac,0x1e10),'st_write_comp':(0x248c,0x2620),'ioctl':(0x1e10,0x23f0),'core_cb_start':(0x10f0,0x11bc)}
if __name__=='__main__':
    res={}
    for tag,p in (('orig',u.ORIG),('cand',u.CAND)):
        code,rel,_=lits(p);res[tag]={k:resolve(code,rel,*v) for k,v in RANGES.items()}
    res['bss_size']='0x44';res['mocked']=False;res['limitations']='Static literal-pool resolution only; no execution.'
    Path=__import__('pathlib').Path
    Path(sys.argv[1]).write_text(json.dumps(res,indent=1))
    for k,v in res['orig'].items():
        print(k);[print('  ',x['at'],x['section_or_symbol'],x['addend']) for x in v]
