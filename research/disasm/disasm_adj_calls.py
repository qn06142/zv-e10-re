import os
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection
from elftools.elf.relocation import RelocationSection
TOOLS = r"C:\Users\Minhsnguhoa\pmca-re\tools"
elf = ELFFile(open(os.path.join(TOOLS, "adjstctl.elf"), "rb"))

# 1) what external symbols does it reference (dynamic/static imports)?
print("=== all defined+undefined symbols referenced by name ===")
names = set()
symtab = None
for s in elf.iter_sections():
    if isinstance(s, SymbolTableSection):
        symtab = s; break
for sym in symtab.iter_symbols():
    if sym.name:
        names.add(sym.name)
for n in sorted(names):
    print("  " + n)

# 2) the entry (0x89cd) and cmdline_init (0x896c) — disassemble to see what they call
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
text = elf.get_section_by_name(".text")
code = text.data(); base = text["sh_addr"]
def disasm_at(va, n=80):
    off = va - base
    if off < 0 or off + n*4 > len(code):
        print("  (range)"); return
    print("--- @0x%x ---" % va)
    for ins in md.disasm(code[off:off+n*4], va):
        print("  0x%08x: %-10s %s" % (ins.address, ins.mnemonic, ins.op_str))

print("\n=== entry (0x89cd) ===")
disasm_at(0x89cd, 40)
print("\n=== cmdline_init (0x896c) ===")
disasm_at(0x896c, 60)
