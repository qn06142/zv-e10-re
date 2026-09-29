import os
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection
K = r"C:\Users\Minhsnguhoa\pmca-re\kmod\osal_uipc.ko"
elf = ELFFile(open(K, "rb"))
text = elf.get_section_by_name(".text")
code = text.data(); base = text["sh_addr"]
symtab = None
for s in elf.iter_sections():
    if isinstance(s, SymbolTableSection):
        symtab = s; break
syms = {sym.name: sym["st_value"] for sym in symtab.iter_symbols() if sym.name}
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
def disasm_at(name, n=140):
    va = syms.get(name)
    if va is None: print("!! %s missing" % name); return
    off = va - base
    if off < 0 or off + n*4 > len(code): print("!! %s range" % name); return
    print("\n=== %s @0x%x ===" % (name, va))
    for ins in md.disasm(code[off:off+n*4], va):
        print("  0x%08x: %-10s %s" % (ins.address, ins.mnemonic, ins.op_str))
# look at dynamic_id fully + snd_msg + the proc_write (another userspace input)
disasm_at("__k_4u_dynamic_id", 160)
disasm_at("__k_4u_snd_msg", 120)
disasm_at("__k_uipc_proc_write", 120)
