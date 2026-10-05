from pathlib import Path
from elftools.elf.elffile import ELFFile

HERE = Path(__file__).resolve().parent.parent.parent
lib_mpr_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libmpr.so"

with open(lib_mpr_path, "rb") as f:
    elf = ELFFile(f)
    print("=== FeaIf and MprIf methods in libmpr.so ===")
    for sname in [".dynsym", ".symtab"]:
        sec = elf.get_section_by_name(sname)
        if not sec: continue
        for sym in sec.iter_symbols():
            n = sym.name
            if any(c in n for c in ["FeaIf", "MprIf"]) and any(k in n for k in ["Aspect", "Scan", "Size", "Crop", "Rec", "Format"]):
                addr = sym['st_value'] & ~1
                size = sym['st_size']
                print(f"  0x{addr:06x} ({size:4d} bytes): {n}")
