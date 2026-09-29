import os, re
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
TOOLS = (ROOT_REPO / 'tools').as_posix()
LOAD_VADDR = 0x8000
f = open(os.path.join(TOOLS, "crypter.elf"), "rb"); data = f.read()
elf = ELFFile(f)
symtab = next((s for s in elf.iter_sections() if isinstance(s, SymbolTableSection)), None)
syms = {s.name: s["st_value"] for s in symtab.iter_symbols() if s.name}
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)

def disasm_at(va, n=160, cap=200):
    off = va - LOAD_VADDR
    if off < 0 or off + n*4 > len(data):
        print("!! range va=0x%x off=0x%x len=%d" % (va, off, len(data))); return
    print("\n=== @0x%x ===" % va)
    for i, ins in enumerate(md.disasm(data[off:off+n*4], va)):
        if i >= cap: break
        print("  0x%08x: %-10s %s" % (ins.address, ins.mnemonic, ins.op_str))

# the scramble routine + nearby (likely references a key table)
for sym in ("Dec_ScrambleInit",):
    if sym in syms:
        disasm_at(syms[sym], 200, 200)

# find all MsDecryptorModule / DecryptorModule member funcs
print("\n=== MsDecryptorModule / DecryptorModule members ===")
for n, v in sorted(syms.items()):
    if "DecryptorModule" in n or "CryptBufferManager" in n or "Scramble" in n or "GetBody" in n:
        print("  0x%08x  %s" % (v, n))
