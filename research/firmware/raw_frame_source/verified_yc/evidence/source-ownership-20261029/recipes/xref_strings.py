from own import *
import struct
def xrefs(targets):
    """ldr rX,[pc,#imm]; add rX,pc within 4 insns resolving to each target string address."""
    res={t:[] for t in targets}
    for off in range(0,len(DATA)-0x20,2):
        h=struct.unpack_from('<H',DATA,off)[0]
        if (h&0xf800)==0x4800:
            rt=(h>>8)&7;la=((BASE+off+4)&~3)+(h&0xff)*4
            if la-BASE+4>len(DATA):continue
            lit=word(la)
            for k in range(1,5):
                h2=struct.unpack_from('<H',DATA,off+2*k)[0]
                if (h2&0xff78)==0x4478 and (h2&7)==rt:
                    t=(lit+BASE+off+2*k+4)&0xffffffff
                    if t in res:res[t].append(hex(BASE+off))
    return res
