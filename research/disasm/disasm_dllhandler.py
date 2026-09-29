import os, re
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection
TOOLS = r"C:\Users\Minhsnguhoa\pmca-re\tools"
LOAD_VADDR = 0x8000
f = open(os.path.join(TOOLS, "crypter.elf"), "rb"); data = f.read()
elf = ELFFile(f)
symtab = next((s for s in elf.iter_sections() if isinstance(s, SymbolTableSection)), None)
syms = {s.name: s["st_value"] for s in symtab.iter_symbols() if s.name}
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)

def disasm_at(va, n=160, cap=200, label=""):
    off = va - LOAD_VADDR
    if off < 0 or off + n*4 > len(data):
        print("!! range va=0x%x off=0x%x len=%d" % (va, off, len(data))); return
    print("\n=== %s @0x%x ===" % (label or ("0x%x"%va), va))
    for i, ins in enumerate(md.disasm(data[off:off+n*4], va)):
        if i >= cap: break
        print("  0x%08x: %-10s %s" % (ins.address, ins.mnemonic, ins.op_str))

# DllHandler::Open - is it dlopen of a hardcoded path?
if "_ZN7Updater10DllHandler4OpenEPKci" in syms:
    disasm_at(syms["_ZN7Updater10DllHandler4OpenEPKci"], 200, 200, "DllHandler::Open")
else:
    print("DllHandler::Open not in dynsym (it's in a .so). Looking for dlopen callers in crypter.elf main...")

# Also: who references the 'bodylib/libupdaterbody.so' string? find xref (ldr rN, [pc, #off] loading its address)
target = b"/tmp_updater/updater/bodyfs/bodylib/libupdaterbody.so"
if target in data:
    tpos = data.find(target)
    tva = LOAD_VADDR + tpos
    print("\nbodylib path string at file 0x%x / va 0x%x" % (tpos, tva))
    # scan .text for ldr rx, [pc, #imm] that lands near tva
    text = elf.get_section_by_name(".text")
    ta, ts = text["sh_addr"], text["sh_size"]
    for ins in md.disasm(data[ta-LOAD_VADDR:ta-LOAD_VADDR+ts], ta):
        if ins.mnemonic == "ldr" and "pc" in ins.op_str:
            # compute target of ldr rx, [pc, #imm]
            m = re.search(r"\[pc, #(-?0x?[0-9a-fA-F]+)\]", ins.op_str)
            if m:
                imm = int(m.group(1), 0)
                ref = (ins.address + 8 + imm) & ~3
                if ref == tva:
                    print("  xref at 0x%x -> bodylib string" % ins.address)
