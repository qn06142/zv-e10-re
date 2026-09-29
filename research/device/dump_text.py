import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
UP = r"C:\Users\Minhsnguhoa\pmca-re\fw_update\updater\FirmwareUpdaterEg.exe"
pe = pefile.PE(UP)
s = [x for x in pe.sections if x.Name.rstrip(b'\x00')==b'.text'][0]
va = pe.OPTIONAL_HEADER.ImageBase + s.VirtualAddress
code = bytes(s.get_data())
md = Cs(CS_ARCH_X86, CS_MODE_32)
lines = []
for ins in md.disasm(code, va):
    a = va + ins.address
    lines.append("%08x: %-10s %s" % (a, ins.mnemonic, ins.op_str))
OUT = r"C:\Users\Minhsnguhoa\pmca-re\disasm_text.txt"
open(OUT,"w").write("\n".join(lines))
print("wrote", len(lines), "to", OUT)
# print the helper + 70 lines
for i,l in enumerate(lines):
    if l.startswith("0040df5b:"):
        for l2 in lines[i-2:i+70]:
            print(l2)
        break
else:
    print("helper not found in linear disasm (capstone may have stopped). searching near 40df5b...")
    # find closest
    for l in lines:
        if "40df" in l:
            print(l)
