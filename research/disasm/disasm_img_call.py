import os, re, struct
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

UP = r"C:\Users\Minhsnguhoa\pmca-re\fw_update\updater\FirmwareUpdaterEg.exe"
pe = pefile.PE(UP)
print("=== imports (via pefile) ===")
try:
    for entry in pe.DIRECTORY_ENTRY_IMPORT:
        funcs = [e.name.decode() if e.name else "ord%d"%e.ordinal for e in entry.imports]
        print("  %s: %s" % (entry.dll.decode(), ", ".join(funcs[:60])))
except Exception as e:
    print("  import parse err:", e)

# text section
text = None
for s in pe.sections:
    if s.Name.rstrip(b"\x00") == b".text":
        text = s; break
print("\n.text va=%#x raw=%#x size=%#x" % (text.VirtualAddress, text.PointerToRawData, text.SizeOfRawData))
code = bytes(text.get_data())
base = pe.OPTIONAL_HEADER.ImageBase
md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True

# 1) locate FDAT string + find xrefs (code referencing its VA)
fdat_off = None
for s in pe.sections:
    d = bytes(s.get_data())
    idx = d.find(b"FDAT")
    if idx >= 0:
        fdat_off = base + s.VirtualAddress + idx
        print("\nFDAT string at VA %#x (section %s)" % (fdat_off, s.Name.rstrip(b'\x00').decode()))
        break

# 2) find DeviceIoControl calls
print("\n=== DeviceIoControl call sites + nearby insns ===")
# DeviceIoControl is imported; find its IAT thunk, then CALL rel32 to it, or inline.
# Simpler: scan disasm for call to imported func by resolving IAT.
# Build import name -> VA map (first thunk)
imp_va = {}
for entry in pe.DIRECTORY_ENTRY_IMPORT:
    dll = entry.dll.decode()
    for e in entry.imports:
        if e.name:
            imp_va[e.name.decode()] = e.address  # IAT VA (where the pointer lives)
# Disassemble whole .text, find calls to DeviceIoControl / CreateFileA/W / WriteFile
def va_of(ins): return base + text.VirtualAddress + ins.address

count = 0
for ins in md.disasm(code, base + text.VirtualAddress):
    if ins.mnemonic == "call" and ins.op_str:
        # resolve target if it's an indirect call through IAT (call dword ptr [IAT_va])
        m = re.match(r"dword ptr \[(\w+)\]", ins.op_str)
        if m:
            tgt = int(m.group(1), 16)
            for nm, va in imp_va.items():
                if va == tgt and nm in ("DeviceIoControl","CreateFileA","CreateFileW","WriteFile","ReadFile"):
                    # print context: preceding 6 insns
                    print("  %#x: CALL %s" % (va_of(ins), nm))
                    count += 1
print("total transport call sites:", count)
