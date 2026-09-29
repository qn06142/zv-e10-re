import os, struct
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
K = (ROOT_REPO / 'kmod/osal_uipc.ko').as_posix()
elf = ELFFile(open(K, "rb"))
print("=== %s ===" % os.path.basename(K))
print("type:", elf.header["e_type"], "machine:", elf.header["e_machine"], "entry: 0x%x" % elf.header["e_entry"])

# sections of interest
for s in elf.iter_sections():
    n = s.name
    if n in (".text", ".init.text", ".exit.text", ".rodata", ".data", ".bss") or "uipc" in n.lower():
        print("  sec %-16s 0x%x %d B" % (n, s["sh_addr"], s["sh_size"]))

# symbols: find handlers (ioctl, write, read, recv, parse, copy_from_user, etc.)
symtab = None
for s in elf.iter_sections():
    if isinstance(s, SymbolTableSection):
        symtab = s; break
funcs = {}
for sym in symtab.iter_symbols():
    if sym["st_info"]["type"] == "STT_FUNC" and sym.name:
        funcs[sym.name] = sym["st_value"]
print("\n=== FUNCs (%d) ===" % len(funcs))
for n, v in sorted(funcs.items(), key=lambda kv: kv[1]):
    print("  0x%08x  %s" % (v, n))

# string refs that indicate the userspace interface
data = open(K, "rb").read()
print("\n=== interface hints ===")
for needle in (b"uipc", b"ioctl", b"copy_from_user", b"copy_to_user", b"device_create",
               b"class_create", b"probe", b"file_operations", b"misc", b"read", b"write"):
    c = data.count(needle)
    if c:
        print("  %-16s x%d" % (needle.decode(), c))
