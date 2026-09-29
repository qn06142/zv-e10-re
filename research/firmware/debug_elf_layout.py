import os, struct
from elftools.elf.elffile import ELFFile
TOOLS = r"C:\Users\Minhsnguhoa\pmca-re\tools"
for name in ("sndcmd.elf", "crypter.elf"):
    elf = ELFFile(open(os.path.join(TOOLS, name), "rb"))
    print("\n==== %s ====" % name)
    print("type", elf.header["e_type"], "entry 0x%x" % elf.header["e_entry"])
    for s in elf.iter_sections():
        if s.name in (".text", ".rodata", ".data") or s["sh_size"] > 100:
            print("  %-12s addr=0x%x off=0x%x size=0x%x" % (s.name, s["sh_addr"], s["sh_offset"], s["sh_size"]))
    # program headers
    for ph in elf.iter_segments():
        if ph["p_type"] == "PT_LOAD":
            print("  LOAD vaddr=0x%x filesz=0x%x memsz=0x%x off=0x%x" % (
                ph["p_vaddr"], ph["p_filesz"], ph["p_memsz"], ph["p_offset"]))
