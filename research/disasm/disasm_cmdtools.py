import os
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection
TOOLS = r"C:\Users\Minhsnguhoa\pmca-re\tools"
LOAD_VADDR = 0x8000  # PT_LOAD vaddr for these ET_EXEC (off 0)

def load_raw(name):
    f = open(os.path.join(TOOLS, name), "rb")
    elf = ELFFile(f)
    data = f.read()
    symtab = next((s for s in elf.iter_sections() if isinstance(s, SymbolTableSection)), None)
    syms = {s.name: s["st_value"] for s in symtab.iter_symbols() if s.name}
    return data, syms

def disasm(name, fns, n=200, cap=200):
    data, syms = load_raw(name)
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    print("\n################ %s ################" % name)
    for fn in fns:
        if fn not in syms:
            cand = [k for k in syms if fn in k]
            if not cand:
                print("\n!! %s not found (%d syms)" % (fn, len(syms))); continue
            va = syms[cand[0]]; print("\n=== %s (matched %s) @0x%x ===" % (fn, cand[0], va))
        else:
            va = syms[fn]; print("\n=== %s @0x%x ===" % (fn, va))
        off = va - LOAD_VADDR
        if off < 0 or off + n*4 > len(data):
            print("!! range off=0x%x len=%d" % (off, len(data))); continue
        for i, ins in enumerate(md.disasm(data[off:off+n*4], va)):
            if i >= cap: break
            print("  0x%08x: %-10s %s" % (ins.address, ins.mnemonic, ins.op_str))

disasm("sndcmd.elf", ["main", "cmdline_init", "cmdline_get_size", "cmdline_get_id", "testcmd_sndmsg"], 220, 220)

# crypter: demangled C++ decryptor syms
data, syms = load_raw("crypter.elf")
dec = [k for k in syms if "Decrypt" in k or "GetBody" in k][:8]
print("\n=== crypter Decryptor/GetBody syms (%d of %d) ===" % (len(dec), len(syms)))
for d in dec:
    print("  0x%08x  %s" % (syms[d], d))
disasm("crypter.elf", dec, 200, 200)
