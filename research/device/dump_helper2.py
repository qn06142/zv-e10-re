import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
UP = (ROOT_REPO / 'fw_update/updater/FirmwareUpdaterEg.exe').as_posix()
pe = pefile.PE(UP)
s = [x for x in pe.sections if x.Name.rstrip(b'\x00')==b'.text'][0]
va0 = pe.OPTIONAL_HEADER.ImageBase + s.VirtualAddress   # 0x401000
target = 0x40df5b
file_off = (target - va0) + s.PointerToRawData           # file offset of the helper
print("helper target VA", hex(target), "file_off", hex(file_off))
raw = bytes(s.get_data())
chunk = raw[file_off:file_off+300]
md = Cs(CS_ARCH_X86, CS_MODE_32)
print("=== disasm of 0x40df5b (SPT init / CDB setter) ===")
for ins in md.disasm(chunk, target):
    a = target + ins.address
    print("%08x: %-10s %s" % (a, ins.mnemonic, ins.op_str))
    if a > target+260: break
