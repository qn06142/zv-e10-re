import os, sys
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection

SO = (ROOT_REPO / 'udtrbody_extract/bodylib/libupdaterbody.so').as_posix()
with open(SO,"rb") as f:
    e = ELFFile(f)
    print("type:", e.header['e_type'], "machine:", e.header['e_machine'])
    dynsym = None
    for s in e.iter_sections():
        if isinstance(s, SymbolTableSection) and s.name == ".dynsym":
            dynsym = s
    if dynsym:
        print("=== exported FUNCTIONS (dynsym, FUNC/OBJECT) ===")
        for sym in dynsym.iter_symbols():
            info = sym['st_info']['type']
            if info in ('STT_FUNC','STT_OBJECT') and sym.name:
                print("  %-40s 0x%x" % (sym.name, sym['st_value']))
    else:
        print("no .dynsym")

# also interesting strings
data = open(SO,"rb").read()
import re

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{5,}", data)]
print("\n=== notable strings ===")
for s in sorted(set(strs)):
    if re.search(r"update|Update|firm|Firm|body|Body|dlopen|load|Load|exec|Exec|start|Start|"
                 r"main|Main|init|Init|run|Run|version|Version|Dll|dll|entry|Entry|"
                 r"write|Write|flash|Flash|nand|NAND|spi|SPI|partition|Partition", s, re.I):
        print("  " + s)
