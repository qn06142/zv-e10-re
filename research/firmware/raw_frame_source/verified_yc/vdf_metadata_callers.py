from pathlib import Path
import array,json
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
b=Path(r'D:/02_Development_And_Projects/pmca-re/dumps/firmware/av-cam.bin').read_bytes();base=0x635c6000;h=array.array('H',b);targets={0x6374ae88:'vdf_metadata_builder'};dec=Cs(CS_ARCH_ARM,CS_MODE_THUMB);hits=[];lines=[]
for index in range(len(h)-1):
 a,c=h[index],h[index+1]
 if a&0xf800!=0xf000 or c&0xd000 not in [0xd000,0x9000]:continue
 s=(a>>10)&1;j1=(c>>13)&1;j2=(c>>11)&1;i1=1^(j1^s);i2=1^(j2^s)
 value=(s<<24)|(i1<<23)|(i2<<22)|((a&1023)<<12)|((c&2047)<<1)
 if s:value-=1<<25
 dest=(base+index*2+4+value)&0xffffffff
 if dest not in targets:continue
 at=base+index*2;hits.append(hex(at));lines.append('\nCALL '+hex(at))
 start=max(0,index*2-100)
 for ins in dec.disasm(b[start:index*2+20],base+start):lines.append(f'{ins.address:08x}: {ins.mnemonic:8} {ins.op_str}')
Path('outputs/yc-source-re-20261025/vdf-metadata-callers.txt').write_text('\n'.join(lines));Path('outputs/yc-source-re-20261025/vdf-metadata-callers.json').write_text(json.dumps(hits,indent=2));print(len(hits),'direct constructor callsites');print(hits)
