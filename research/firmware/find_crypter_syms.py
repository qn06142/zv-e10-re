import os, re
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection
TOOLS = r"C:\Users\Minhsnguhoa\pmca-re\tools"
elf = ELFFile(open(os.path.join(TOOLS, "crypter.elf"), "rb"))
symtab = next((s for s in elf.iter_sections() if isinstance(s, SymbolTableSection)), None)
syms = {s.name: s["st_value"] for s in symtab.iter_symbols() if s.name}
# mangled C++ names containing Decrypt/GetBody/Body
print("=== mangled decryptor-related syms ===")
for n, v in sorted(syms.items()):
    if re.search(r"Decrypt|GetBody|Body|Crypt|9Updater|ApiException", n):
        print("  0x%08x  %s" % (v, n))
