from pathlib import Path
from elftools.elf.elffile import ELFFile
import capstone

HERE = Path(__file__).resolve().parent.parent.parent
lib_dir = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib"
cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)

def disasm_func(lib_name, sym_name):
    path = lib_dir / lib_name
    with open(path, "rb") as f:
        elf = ELFFile(f)
        symtab = elf.get_section_by_name(".dynsym")
        for sym in symtab.iter_symbols():
            if sym.name == sym_name:
                addr = sym['st_value'] & ~1
                size = sym['st_size']
                print(f"=== {sym_name} in {lib_name} at 0x{addr:06x} ({size} bytes) ===")
                f.seek(addr)
                code = f.read(size if size > 0 else 64)
                for insn in cs.disasm(code, addr):
                    print(f"  0x{insn.address:06x}: {insn.mnemonic} {insn.op_str}")
                return
    print(f"[-] Symbol {sym_name} not found in {lib_name}")

if __name__ == "__main__":
    disasm_func("libmprctrl.so", "_ZN13UtilStillSize14CnvMovieAspectEi")
    disasm_func("libmprctrl.so", "_ZN13UtilStillSize16GetContentAspectENS_8RectSizeE")
    disasm_func("libmpr.so", "_ZN5MprIf12SetRecAspectEPNS_12VAspectParamEm")
    disasm_func("libmpr.so", "_ZN5MprIf16SetRecTvScanModeEPNS_11TvScanParamEm")
