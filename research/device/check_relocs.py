from pathlib import Path
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection

HERE = Path(__file__).resolve().parent.parent.parent
lib_obj_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

with open(lib_obj_path, "rb") as f:
    elf = ELFFile(f)
    rel_dyn = elf.get_section_by_name(".rel.dyn")
    print("=== Relocations around 0x1369220 ===")
    for rel in rel_dyn.iter_relocations():
        if 0x1369200 <= rel['r_offset'] <= 0x1369400:
            print(f"  offset: 0x{rel['r_offset']:08x}, type: {rel['r_info_type']}, sym: {rel['r_info_sym']}")
