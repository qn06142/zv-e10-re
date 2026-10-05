from pathlib import Path
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection
import struct

HERE = Path(__file__).resolve().parent.parent.parent
lib_obj_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

with open(lib_obj_path, "rb") as f:
    elf = ELFFile(f)
    rel_plt = elf.get_section_by_name(".rel.plt")
    dynsym = elf.get_section_by_name(".dynsym")
    
    enter_rec_got = None
    for rel in rel_plt.iter_relocations():
        sym = dynsym.get_symbol(rel['r_info_sym'])
        if "EnterRec" in sym.name:
            print(f"Relocation for {sym.name}: GOT offset 0x{rel['r_offset']:08x}")
            enter_rec_got = rel['r_offset']

# Now find references to enter_rec_got or its PLT stub
if enter_rec_got:
    with open(lib_obj_path, "rb") as f:
        data = f.read()
    tb = struct.pack('<I', enter_rec_got)
    pos = 0
    while True:
        idx = data.find(tb, pos)
        if idx == -1: break
        print(f"GOT address referenced at 0x{idx:08x}")
        pos = idx + 1
