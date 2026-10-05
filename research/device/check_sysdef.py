from pathlib import Path
from elftools.elf.elffile import ELFFile

HERE = Path(__file__).resolve().parent.parent.parent
sysdef_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libSysDef.so"

with open(sysdef_path, "rb") as f:
    elf = ELFFile(f)
    print("=== Symbols in libSysDef.so ===")
    count = 0
    for sname in [".dynsym", ".symtab"]:
        sec = elf.get_section_by_name(sname)
        if not sec: continue
        for sym in sec.iter_symbols():
            n = sym.name
            if any(k in n.lower() for k in ["param", "aspect", "prm", "ratio", "movie"]):
                print(f"  [{sname}] {sym.name} @ 0x{sym['st_value']:08x} (size {sym['st_size']})")
                count += 1
                if count > 50:
                    print("  ... (truncated)")
                    break
