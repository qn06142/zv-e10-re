import struct
from pathlib import Path
from elftools.elf.elffile import ELFFile
import capstone

HERE = Path(__file__).resolve().parent.parent.parent
p = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

def rot(w):
    imm8 = w & 0xFF
    r = ((w >> 8) & 0xF) * 2
    return ((imm8 >> r) | (imm8 << (32 - r))) & 0xFFFFFFFF if r else imm8

with open(p, "rb") as f:
    elf = ELFFile(f)
    syms = list(elf.get_section_by_name(".dynsym").iter_symbols())
    targets = {}
    for r in elf.get_section_by_name(".rel.plt").iter_relocations():
        n = syms[r['r_info_sym']].name
        if "SetRecAspect" in n or "SetRecTvScanMode" in n:
            targets[r['r_offset']] = n
    plt = elf.get_section_by_name(".plt")
    pa, pd = plt['sh_addr'], plt.data()
    stubs = {}
    for i in range(0, len(pd) - 12, 4):
        a, b, c = struct.unpack_from('<III', pd, i)
        if (a & 0xFFFFF000) == 0xE28FC000 and (b & 0xFFFFF000) == 0xE28CC000 and (c & 0xFFFFF000) == 0xE5BCF000:
            got = pa + i + 8 + rot(a) + rot(b) + (c & 0xFFF)
            if got in targets:
                stubs[pa + i] = targets[got]
                print(f"PLT 0x{pa+i:08x} -> {targets[got]}")
    text = elf.get_section_by_name(".text")
    ta, td = text['sh_addr'], text.data()
    # thumb BL/BLX decode
    for i in range(0, len(td) - 4, 2):
        h1, h2 = struct.unpack_from('<HH', td, i)
        if (h1 & 0xF800) == 0xF000 and (h2 & 0xC000) == 0xC000 and (h2 & 0x1000 or True):
            s = (h1 >> 10) & 1
            j1 = (h2 >> 13) & 1; j2 = (h2 >> 11) & 1
            i1 = (~(j1 ^ s)) & 1; i2 = (~(j2 ^ s)) & 1
            v = (s << 24) | (i1 << 23) | (i2 << 22) | ((h1 & 0x3FF) << 12) | ((h2 & 0x7FF) << 1)
            if v & 0x1000000: v -= 0x2000000
            tgt = ta + i + 4 + v
            if not (h2 & 0x1000):  # blx
                tgt &= ~3
                tgt = ((ta + i + 4) & ~3) + v
            if tgt in stubs:
                print(f"call at 0x{ta+i:08x} -> {stubs[tgt]}")

