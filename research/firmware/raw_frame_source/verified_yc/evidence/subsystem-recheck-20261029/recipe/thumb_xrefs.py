"""Conservative Thumb immediate-call candidates, validated with Capstone."""
import struct
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB

def direct_calls(data,base):
 cs=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
 for off in range(0,len(data)-3,2):
  a,b=struct.unpack_from('<HH',data,off)
  if a&0xf800!=0xf000 or b&0xc000!=0xc000:continue
  i=next(cs.disasm(data[off:off+4],base+off),None)
  if i and i.size==4 and i.mnemonic in ['bl','blx'] and i.op_str.startswith('#0x'):yield i.address,int(i.op_str[1:],16)
