import os
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
ROOT = (ROOT_REPO / 'kmod').as_posix()
K = os.path.join(ROOT, "dmm.ko")
elf = ELFFile(open(K, "rb"))
text = elf.get_section_by_name(".text"); code = text.data(); base = text["sh_addr"]
symtab = None
for s in elf.iter_sections():
    if isinstance(s, SymbolTableSection): symtab = s; break
syms = {sym.name: sym["st_value"] for sym in symtab.iter_symbols() if sym.name}
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
def disasm_at(name, n=110, cap=140):
    va = syms.get(name)
    if va is None: print("!! %s missing" % name); return
    off = va - base
    if off < 0 or off + n*4 > len(code): print("!! %s range" % name); return
    print("\n=== %s @0x%x ===" % (name, va))
    for i, ins in enumerate(md.disasm(code[off:off+n*4], va)):
        if i >= cap: break
        print("  0x%08x: %-10s %s" % (ins.address, ins.mnemonic, ins.op_str))

# the cross-world handlers: how does a unit/map index get used?
for fn in ("dmm_CallbackHandler", "dmm_ctrl_OpenUnitHdlr", "dmm_ctrl_LoadExtraMapHdlr",
           "dmm_ext_ctrl_LoadExtraMap", "dmm_unit_ctrl_Open"):
    disasm_at(fn, 120, 120)

# also: is there a cdev/ioctl in dmm that takes userspace input?
print("\n=== dmm cdev/ioctl-ish ===")
for fn in ("dmm_module_InitModule", "init_module"):
    disasm_at(fn, 80, 80)
