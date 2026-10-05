import sys
from pathlib import Path
from elftools.elf.elffile import ELFFile
import capstone

HERE = Path(__file__).resolve().parent.parent.parent
libmpr_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libmpr.so"
cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
cs.detail = True

def inspect_symbol(name, max_len=0x400):
    with open(libmpr_path, "rb") as f:
        elf = ELFFile(f)
        symtab = elf.get_section_by_name(".dynsym")
        target_sym = None
        for sym in symtab.iter_symbols():
            if sym.name == name:
                target_sym = sym
                break
        if not target_sym:
            print(f"[-] Symbol {name} not found")
            return
        
        addr = target_sym['st_value'] & ~1
        size = target_sym['st_size'] or max_len
        print(f"=== {name} at 0x{addr:08x} (size: {size}) ===")
        f.seek(addr)
        code = f.read(min(size, max_len))
        for insn in cs.disasm(code, addr):
            print(f"  0x{insn.address:06x}: {insn.mnemonic:10s} {insn.op_str}")

if __name__ == "__main__":
    inspect_symbol("_ZN7FeaCore12SetRecAspectEPN5MprIf12VAspectParamEm")
    print("\n" + "="*60 + "\n")
    inspect_symbol("_ZN7FeaCore16SetRecDefinitionEPN5MprIf16VResolutionParamEm")
    print("\n" + "="*60 + "\n")
    inspect_symbol("_ZN7FeaCore16SetRecTvScanModeEPN5MprIf11TvScanParamEm")
    print("\n" + "="*60 + "\n")
    inspect_symbol("_ZN7FeaCore19CreateEnterRecParamEPN5MprIf13EnterRecParamEP4MMgrS4_PN11RecorderDef13EnterRecParamE", max_len=0x600)
