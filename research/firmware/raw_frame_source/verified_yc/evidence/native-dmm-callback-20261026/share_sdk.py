from pathlib import Path
from elftools.elf.elffile import ELFFile
from capstone import *
p=Path(r'D:/02_Development_And_Projects/pmca-re/dumps/camera_2025/usr/usr/lib/libBizFw.so')
with p.open('rb') as f:
 e=ELFFile(f);t=e.get_section_by_name('.text');b=t.data();base=t['sh_addr'];d=Cs(CS_ARCH_ARM,CS_MODE_THUMB);d.skipdata=True
 for i in d.disasm(b[0x35f9c-base:0x360a4-base],0x35f9c):print(hex(i.address),i.mnemonic,i.op_str)
