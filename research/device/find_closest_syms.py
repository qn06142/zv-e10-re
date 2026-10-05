from pathlib import Path
from elftools.elf.elffile import ELFFile

HERE = Path(__file__).resolve().parent.parent.parent
lib_obj_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

with open(lib_obj_path, "rb") as f:
    elf = ELFFile(f)
    symtab = elf.get_section_by_name(".dynsym")
    closest = []
    for sym in symtab.iter_symbols():
        val = sym['st_value']
        diff = abs(val - 0x01369220)
        if diff < 0x2000:
            closest.append((diff, val, sym.name, sym['st_size']))
    closest.sort()
    print("Closest symbols to 0x01369220:")
    for diff, val, name, size in closest[:10]:
        print(f"  0x{val:08x} (+{diff:#x}): {name} (size {size})")
