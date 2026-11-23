"""Shared offline helpers: RTTI->vtable lookup and disassembly of original av-cam.bin (read-only)."""
from rtos import *
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB,CS_MODE_ARM
def rtti_vtables(mangled):
    """Return [(typeinfo_addr, vtable_addr, [first 12 slots])] for a mangled class name (no leading N..E decoration needed: pass bytes)."""
    out=[]
    name=BASE+DATA.index(mangled)
    for r in refs(name):
        ti=r-4
        for p in refs(ti):
            out.append((ti,p+4,[word(p+4+4*j) for j in range(12)]))
    return out
def dis(a,n=0x100,arm=False):
    d=Cs(CS_ARCH_ARM,CS_MODE_ARM if arm else CS_MODE_THUMB);d.skipdata=True
    a&=~1
    return disasm(a,a+n)
