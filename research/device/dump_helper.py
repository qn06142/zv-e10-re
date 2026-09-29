import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
UP = r"C:\Users\Minhsnguhoa\pmca-re\fw_update\updater\FirmwareUpdaterEg.exe"
pe = pefile.PE(UP)
print("ImageBase =", hex(pe.OPTIONAL_HEADER.ImageBase))
for s in pe.sections:
    print("  section", s.Name.rstrip(b'\x00').decode(), "VA", hex(s.VirtualAddress), "raw", hex(s.PointerToRawData), "size", hex(s.SizeOfRawData))
# The helper 0x40df5b: find which section contains VA 0x40df5b
target = 0x40df5b
for s in pe.sections:
    va = pe.OPTIONAL_HEADER.ImageBase + s.VirtualAddress
    if va <= target < va + s.SizeOfRawData:
        print("helper 0x40df5b lives in", s.Name.rstrip(b'\x00').decode(), "section-base VA", hex(va))
        code = bytes(s.get_data())
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        out = []
        for ins in md.disasm(code, va):
            a = va + ins.address
            out.append("%08x: %-10s %s" % (a, ins.mnemonic, ins.op_str))
            if a == target:
                # print this + next 60
                idx = len(out)-1
                print("\n=== helper 0x40df5b (SPT init / CDB setter) ===")
                for l in out[max(0,idx-3):idx+60]:
                    print(l)
                break
        break
