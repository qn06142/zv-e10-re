import os
from pathlib import Path
from elftools.elf.elffile import ELFFile
import capstone

HERE = Path(__file__).resolve().parent.parent.parent
lib_dir = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib"
bin_dir = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "bin"
cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
cs.detail = True

def find_symbols(lib_name, pattern):
    path = lib_dir / lib_name if (lib_dir / lib_name).exists() else bin_dir / lib_name
    print(f"=== Searching symbols matching '{pattern}' in {lib_name} ===")
    with open(path, "rb") as f:
        elf = ELFFile(f)
        for sname in [".dynsym", ".symtab"]:
            symtab = elf.get_section_by_name(sname)
            if not symtab:
                continue
            for sym in symtab.iter_symbols():
                if pattern.lower() in sym.name.lower():
                    print(f"  [{sname}] {sym.name} @ 0x{sym['st_value']:08x} (size {sym['st_size']})")

if __name__ == "__main__":
    find_symbols("libObj.so", "SeqEnc")
    find_symbols("libObj.so", "CalcRatio")
    find_symbols("libObj.so", "Set4K2K")
    find_symbols("libObj.so", "ObjRenderer")
