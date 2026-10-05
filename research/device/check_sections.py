from pathlib import Path
from elftools.elf.elffile import ELFFile

HERE = Path(__file__).resolve().parent.parent.parent
lib_obj_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

with open(lib_obj_path, "rb") as f:
    elf = ELFFile(f)
    print("=== Sections in libObj.so ===")
    for sec in elf.iter_sections():
        sh_addr = sec['sh_addr']
        sh_size = sec['sh_size']
        sh_offset = sec['sh_offset']
        print(f"  {sec.name:20s}: addr=0x{sh_addr:08x}, size=0x{sh_size:08x}, offset=0x{sh_offset:08x}, type={sec['sh_type']}")

    # Find section containing 0x46a08
    for sec in elf.iter_sections():
        if sec['sh_addr'] <= 0x46a08 < sec['sh_addr'] + sec['sh_size']:
            print(f"0x00046a08 is in {sec.name}")
        if sec['sh_addr'] <= 0x1369220 < sec['sh_addr'] + sec['sh_size']:
            print(f"0x01369220 is in {sec.name}")
