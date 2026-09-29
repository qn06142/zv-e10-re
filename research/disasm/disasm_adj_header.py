import os
TOOLS = r"C:\Users\Minhsnguhoa\pmca-re\tools"
data = open(os.path.join(TOOLS, "adjstctl.elf"), "rb").read()
print("size", len(data), "magic", data[:4])
# ELF32 ARM header parse
import struct
e_machine = struct.unpack_from("<H", data, 18)[0]
e_entry = struct.unpack_from("<I", data, 24)[0]
e_phoff = struct.unpack_from("<I", data, 28)[0]
e_shoff = struct.unpack_from("<I", data, 32)[0]
e_phentsize = struct.unpack_from("<H", data, 42)[0]
e_phnum = struct.unpack_from("<H", data, 44)[0]
e_shentsize = struct.unpack_from("<H", data, 46)[0]
e_shnum = struct.unpack_from("<H", data, 48)[0]
print("machine 0x%04x (0x28=ARM)" % e_machine, "entry 0x%08x" % e_entry)
print("phoff", e_phoff, "phnum", e_phnum, "shoff", e_shoff, "shnum", e_shnum)
# find the .text / load segments by scanning program headers
off = e_phoff
for i in range(e_phnum):
    p_type, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_flags, p_align = struct.unpack_from("<8I", data, off)
    if p_type == 1:  # PT_LOAD
        print("LOAD seg %d: off=0x%x vaddr=0x%x filesz=0x%x memsz=0x%x flags=%d" %
              (i, p_offset, p_vaddr, p_filesz, p_memsz, p_flags))
    off += e_phentsize
