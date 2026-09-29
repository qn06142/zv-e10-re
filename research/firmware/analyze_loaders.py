import os
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection
ROOT = r"C:\Users\Minhsnguhoa\pmca-re\kmod"
for name in ("liro.ko", "dmm.ko"):
    elf = ELFFile(open(os.path.join(ROOT, name), "rb"))
    print("\n==== %s ====" % name)
    # sections
    for s in elf.iter_sections():
        if s.name in (".text", ".init.text", ".rodata", ".data") or "load" in s.name.lower() or "init" in s.name.lower():
            print("  sec %-14s 0x%x %dB" % (s.name, s["sh_addr"], s["sh_size"]))
    symtab = None
    for s in elf.iter_sections():
        if isinstance(s, SymbolTableSection):
            symtab = s; break
    funcs = {sym.name: sym["st_value"] for sym in symtab.iter_symbols()
             if sym["st_info"]["type"] == "STT_FUNC" and sym.name}
    # focus on load/init/validate/copy/map/handler-ish names
    keys = ("init", "load", "probe", "open", "copy", "map", "valid", "check",
            "reloc", "handler", "dispatch", "exec", "decrypt", "secure", "key", "auth")
    print("  FUNCs (%d total); load/init/validate-related:" % len(funcs))
    interesting = sorted([(v, n) for n, v in funcs.items()
                          if any(k in n.lower() for k in keys)])
    for v, n in interesting[:40]:
        print("    0x%08x  %s" % (v, n))
