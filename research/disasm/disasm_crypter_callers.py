import os, re
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection
from elftools.elf.relocation import RelocationSection
TOOLS = (ROOT_REPO / 'tools').as_posix()
LOAD_VADDR = 0x8000
f = open(os.path.join(TOOLS, "crypter.elf"), "rb"); data = f.read()
elf = ELFFile(f)
symtab = next((s for s in elf.iter_sections() if isinstance(s, SymbolTableSection)), None)
syms = {s.name: s["st_value"] for s in symtab.iter_symbols() if s.name}
dynsym = elf.get_section_by_name(".dynsym")
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)

# 1) which imported lib provides Dec_ScrambleInit? check .rel.plt for the symbol
print("=== imports: libs ===")
for s in elf.iter_sections():
    if s.name == ".dynsym":
        for r in elf.get_section_by_name(".rel.plt").iter_relocations():
            pass
# simpler: read DT_NEEDED
from elftools.elf.dynamic import DynamicSection

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
for s in elf.iter_sections():
    if isinstance(s, DynamicSection):
        for tag in s.iter_tags():
            if tag.entry.d_tag == "DT_NEEDED":
                print("  NEEDED:", tag.needed)

# 2) find callers of Dec_ScrambleInit: search .text for the PLT bl to 0xa98c
scramble_init_va = syms.get("Dec_ScrambleInit")
print("\nDec_ScrambleInit va=0x%x" % scramble_init_va)
text = elf.get_section_by_name(".text")
taddr, tsize = text["sh_addr"], text["sh_size"]
callers = []
for ins in md.disasm(data[taddr-LOAD_VADDR : taddr-LOAD_VADDR+tsize], taddr):
    if ins.mnemonic == "bl" and ins.op_str == "0x%x" % scramble_init_va:
        callers.append(ins.address)
print("callers of Dec_ScrambleInit:", [hex(c) for c in callers])

# 3) disassemble each caller (the function containing it) - find function bounds by scanning back to a 'push'/'stmfd'
def func_bounds(addr):
    # scan backward for a function prologue (stmfd sp! / push)
    off = addr - LOAD_VADDR
    start = addr
    for i in range(0, 0x400, 4):
        o = off - i
        if o < 0: break
        window = data[o:o+8]
        if window[:2] in (b"\xe9\x2d", b"\xe9\x2d") or window[:2] == b"\xe5\x2d":  # stmfd sp!
            start = addr - i; break
    return start

for c in callers:
    st = func_bounds(c)
    print("\n=== caller func around 0x%x (prologue ~0x%x) ===" % (c, st))
    off = st - LOAD_VADDR
    for i, ins in enumerate(md.disasm(data[off:off+0x200], st)):
        if i > 80: break
        mark = "  <== Dec_ScrambleInit call" if ins.address == c else ""
        print("  0x%08x: %-10s %s%s" % (ins.address, ins.mnemonic, ins.op_str, mark))
