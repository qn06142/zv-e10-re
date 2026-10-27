from pathlib import Path
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
import sys,struct
b=Path('outputs/uvc-startup-fix/candidate-1080p/av-cam.bin').read_bytes();base=0x635c6000
lo=int(sys.argv[1],0);hi=int(sys.argv[2],0);name=sys.argv[3]
rows=[]
for i in Cs(CS_ARCH_ARM,CS_MODE_THUMB).disasm(b[lo-base:hi-base],lo):
 row=f'{i.address:08x}: {i.mnemonic:10} {i.op_str}'
 if i.mnemonic.startswith('ldr') and '[pc' in i.op_str:
  imm=int(i.op_str.split('#')[1].split(']')[0],0) if '#' in i.op_str else 0
  p=((i.address+4)&~3)+imm
  if base<=p<base+len(b)-4:row+=f' ; literal@{p:x}={struct.unpack_from("<I",b,p-base)[0]:08x}'
 rows.append(row)
Path('outputs/yc-codec-audit/'+name+'.txt').write_text('\n'.join(rows)+'\n');print('\n'.join(rows))
