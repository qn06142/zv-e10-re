import os, struct
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
UP = r"C:\Users\Minhsnguhoa\pmca-re\fw_update\updater\FirmwareUpdaterEg.exe"
OUT = r"C:\Users\Minhsnguhoa\pmca-re\disasm_funcs.txt"
pe = pefile.PE(UP)
text = [s for s in pe.sections if s.Name.rstrip(b"\x00")==b".text"][0]
code = bytes(text.get_data()); base = pe.OPTIONAL_HEADER.ImageBase; va0 = base + text.VirtualAddress
# the updater functions live around VA 0x408140..0x408900 (file showed 0x808xxx = 0x400000+0x808?? -> actually va = 0x408140)
# disasm the whole .text and write lines; we'll grep later
md = Cs(CS_ARCH_X86, CS_MODE_32)
lines = []
for ins in md.disasm(code, va0):
    va = va0 + ins.address
    lines.append("%08x: %-10s %s" % (va, ins.mnemonic, ins.op_str))
open(OUT,"w").write("\n".join(lines))
print("wrote", len(lines), "insns to", OUT)
# print the region of interest directly
start_va = 0x408140; end_va = 0x408900
for l in lines:
    va = int(l[:8],16)
    if start_va <= va <= end_va:
        print(l)
