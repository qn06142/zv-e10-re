import os, re
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
TOOLS = (ROOT_REPO / 'tools').as_posix()
name = "crypter.elf"
f = open(os.path.join(TOOLS, name), "rb"); data = f.read()
elf = ELFFile(f)
LOAD_VADDR = 0x8000
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)

print("==== %s (%d B) ====" % (name, len(data)))

# 1) AES S-box anchor (first 16 bytes of the standard AES S-box)
SBOX_ANCHOR = bytes([0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76])
idx = data.find(SBOX_ANCHOR)
print("AES S-box anchor (63 7c 77 7b ...) present:", idx >= 0, ("at off 0x%x" % idx) if idx>=0 else "")
# AES first-word 0x637c777b as little-endian
word = bytes([0x7b,0x77,0x7c,0x63])
print("AES '637c777b' 32-bit word occurrences:", data.count(word))

# 2) crypto-ish strings
hits = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{4,}", data)]
uniq = sorted(set(hits))
for kw in ("AES","DES","RSA","EVP","cbc","ecb","ctr","key","iv","crypt",
           "decrypt","sign","verify","sha","md5","hmac","cert","bodyimg",
           "GetBody","DecryptorModule","BaseBodyLoaderModule"):
    found = [h for h in uniq if kw.lower() in h.lower()]
    if found:
        print("  [%s] -> %s" % (kw, found[:8]))

# 3) mangled C++ symbols
symtab = next((s for s in elf.iter_sections() if isinstance(s, SymbolTableSection)), None)
syms = {s.name: s["st_value"] for s in symtab.iter_symbols() if s.name}
def demangle(n):
    m = re.match(r"_ZN(?:(\d+))?([A-Za-z_]+)", n)
    return m.group(2) if m else n
print("\n=== interesting mangled syms (Updater/Body/Load/Decrypt/Crypt/Key/Sign/Verif) ===")
seen = set()
for n, v in sorted(syms.items()):
    if re.search(r"Updater|Body|Load|Decrypt|Crypt|Get|Set|Init|Update|Image|Img|Key|Sign|Verif", n):
        dm = demangle(n)
        if dm not in seen:
            seen.add(dm); print("  0x%08x  %s  (%s)" % (v, n, dm))
