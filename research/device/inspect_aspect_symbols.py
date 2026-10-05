from pathlib import Path
from elftools.elf.elffile import ELFFile
import capstone

HERE = Path(__file__).resolve().parent.parent.parent
lib_dir = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib"

def dump_symbols(lib_name):
    print(f"=== Symbols in {lib_name} ===")
    path = lib_dir / lib_name
    with open(path, "rb") as f:
        elf = ELFFile(f)
        symtab = elf.get_section_by_name(".dynsym")
        for sym in symtab.iter_symbols():
            name = sym.name
            if any(k in name for k in ["Aspect", "StillSize", "MovieSize", "ScanMode", "Sensor"]):
                print(f"  {name} -> 0x{sym['st_value']:08x} (size {sym['st_size']})")

if __name__ == "__main__":
    for lib in ["libmprctrl.so", "libBizFw.so", "libObj.so", "libSysDef.so"]:
        dump_symbols(lib)
