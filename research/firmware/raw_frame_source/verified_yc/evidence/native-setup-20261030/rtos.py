from pathlib import Path
import struct,hashlib
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
BASE=0x635c6000
DATA=(Path(__file__).resolve().parents[6] / 'dumps/firmware/av-cam.bin').read_bytes()
assert hashlib.md5(DATA).hexdigest()=='cdcae9d4fdbf66a33704a4c7564e346d'
def word(a):return struct.unpack_from('<I',DATA,a-BASE)[0]
def cstr(a):return DATA[a-BASE:].split(b'\0',1)[0].decode('ascii','replace')
def refs(a):
 needle=struct.pack('<I',a);start=0;out=[]
 while True:
  start=DATA.find(needle,start)
  if start<0:return out
  if start%4==0:out.append(BASE+start)
  start+=1

def disasm(start,end):
 out=[];dec=Cs(CS_ARCH_ARM,CS_MODE_THUMB);dec.skipdata=True
 for i in dec.disasm(DATA[start-BASE:end-BASE],start):
  note=''
  if ', [pc, #' in i.op_str and i.op_str.endswith(']'):
   try:
    disp=int(i.op_str.split(', [pc, #')[1][:-1],0);a=((i.address+4)&~3)+disp;v=word(a);note=f' ; [{a:08x}]={v:08x}'
   except Exception:pass
  out.append(f'{i.address:08x}: {i.mnemonic:9} {i.op_str}{note}')
 return '\n'.join(out)+'\n'
if __name__=='__main__':
 for name in [b'N3VDF20SystemCmdPinSendCompE',b'N3VDF24VdfInputReleasePinAndMemE']:
  a=BASE+DATA.index(name);print(name.decode(),hex(a))
  for r in refs(a):
   ti=r-4;print('RTTI',hex(ti),'refs',list(map(hex,refs(ti))))
   for p in refs(ti):print('vtable',hex(p+4),[hex(word(p+4+4*j)) for j in range(8)])
