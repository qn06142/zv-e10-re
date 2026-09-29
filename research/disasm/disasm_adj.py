import os, struct
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
TOOLS = r"C:\Users\Minhsnguhoa\pmca-re\tools"

# Use pyelftools for robust section lookup (installed in venv)
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection

elf = ELFFile(open(os.path.join(TOOLS, "adjstctl.elf"), "rb"))
print("ELF:", elf.header["e_machine"], "entry=0x%x" % elf.header["e_entry"])

# locate .text and symbol table
text = elf.get_section_by_name(".text")
symtab = None
for s in elf.iter_sections():
    if isinstance(s, SymbolTableSection):
        symtab = s; break

# collect symbols of interest: main, cmdline_*, the dispatch, IPC init
interesting = {}
if symtab:
    for sym in symtab.iter_symbols():
        n = sym.name
        if n and any(k in n for k in ("main","cmdline","parse","dispatch","uipc","osal","init","send","recv","exec","Exec","adjust","usage")):
            interesting[n] = sym["st_value"]
print("\n=== interesting symbols (%d) ===" % len(interesting))
for n, v in sorted(interesting.items(), key=lambda kv: kv[1])[:60]:
    print("  0x%08x  %s" % (v, n))

# disassemble .text
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
code = text.data()
base = text["sh_addr"]
print("\n=== .text 0x%x..0x%x (%d bytes) ===" % (base, base+len(code), len(code)))

# disassemble a region around 'main' if found
def disasm_at(va, n=120):
    off = va - base
    if off < 0 or off+n > len(code): 
        print("  (out of range)"); return
    print("--- disasm @0x%x ---" % va)
    for ins in md.disasm(code[off:off+n*4], va):
        print("  0x%08x: %-10s %s" % (ins.address, ins.mnemonic, ins.op_str))

# find main
main_va = None
for n, v in interesting.items():
    if n == "main":
        main_va = v
if main_va:
    disasm_at(main_va, 160)
