import os, re
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]

UP = (ROOT_REPO / 'fw_update/updater/FirmwareUpdaterEg.exe').as_posix()
pe = pefile.PE(UP)
text = [s for s in pe.sections if s.Name.rstrip(b"\x00")==b".text"][0]
code = bytes(text.get_data())
base = pe.OPTIONAL_HEADER.ImageBase
va0 = base + text.VirtualAddress

imp_va = {}
for entry in pe.DIRECTORY_ENTRY_IMPORT:
    for e in entry.imports:
        if e.name:
            imp_va[e.name.decode()] = e.address

md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True
insns = list(md.disasm(code, va0))

def va(i): return va0 + i.address

# find DeviceIoControl call indices
dio_idx = [i for i,ins in enumerate(insns) if ins.mnemonic=="call"
           and re.match(r"dword ptr \[0x[0-9a-fA-F]+\]", ins.op_str)
           and int(re.search(r"0x([0-9a-fA-F]+)", ins.op_str).group(1),16) in imp_va.values()
           and [n for n,a in imp_va.items() if a==int(re.search(r"0x([0-9a-fA-F]+)", ins.op_str).group(1),16)][0]=="DeviceIoControl"]

print("DeviceIoControl call count:", len(dio_idx))
for k, ci in enumerate(dio_idx):
    print("\n===== DeviceIoControl #%d @ %#x =====" % (k+1, va(insns[ci])))
    # print 30 insns before + 4 after, annotate push of IOCTL (2nd arg) and buffer
    start = max(0, ci-30)
    for j in range(start, min(len(insns), ci+5)):
        ins = insns[j]
        mark = " >>>" if j==ci else "    "
        # try to show immediate values meaningfully
        print("  %#08x%s %-10s %s" % (va(ins), mark, ins.mnemonic, ins.op_str))
    # specifically: find the IOCTL code pushed as imm32 in the preceding window
    print("  -- IOCTL candidates (imm32 pushes before call) --")
    for j in range(start, ci):
        ins = insns[j]
        if ins.mnemonic == "push" and re.match(r"0x[0-9a-fA-F]+", ins.op_str):
            val = int(ins.op_str,16)
            if 0x4<<16 <= val <= 0x9<<16 or val > 0x1000:  # typical DeviceIoControl code range
                print("     push %#x (possible IOCTL)" % val)
