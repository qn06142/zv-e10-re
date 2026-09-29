import struct

d = open(r"C:\Users\Minhsnguhoa\pmca-re\fdat_decrypted.bin","rb").read()
N = len(d)
print("image size:", N)

ELF = b"\x7fELF"
off = 0
hits = []
while True:
    i = d.find(ELF, off)
    if i < 0:
        break
    # validate ELF header
    if i + 52 <= N:
        ei_class = d[i+4]      # 1=32bit, 2=64bit
        ei_data  = d[i+5]      # 1=LE, 2=BE
        e_type   = struct.unpack_from("<H", d, i+16)[0]   # ET_EXEC=2, ET_DYN=3
        e_machine= struct.unpack_from("<H", d, i+18)[0]   # 40=ARM, 62=x86-64, 183=ARM64
        if ei_class in (1,2) and ei_data in (1,2):
            # try to read program header total size to estimate file size
            if ei_class == 1:  # 32-bit
                e_phoff = struct.unpack_from("<I", d, i+28)[0]
                e_phentsize = struct.unpack_from("<H", d, i+44)[0]
                e_phnum = struct.unpack_from("<H", d, i+46)[0]
                e_shoff = struct.unpack_from("<I", d, i+32)[0]
                e_shentsize = struct.unpack_from("<H", d, i+48)[0]
                e_shnum = struct.unpack_from("<H", d, i+50)[0]
            else:  # 64-bit
                e_phoff = struct.unpack_from("<Q", d, i+32)[0]
                e_phentsize = struct.unpack_from("<H", d, i+54)[0]
                e_phnum = struct.unpack_from("<H", d, i+56)[0]
                e_shoff = struct.unpack_from("<Q", d, i+40)[0]
                e_shentsize = struct.unpack_from("<H", d, i+58)[0]
                e_shnum = struct.unpack_from("<H", d, i+60)[0]
            # estimate file size from section headers
            est = e_shoff + e_shnum * e_shentsize if e_shoff else 0
            for ph in range(e_phnum):
                if ei_class == 1:
                    po = e_phoff + ph*e_phentsize
                    p_offset = struct.unpack_from("<I", d, po+4)[0]
                    p_filesz = struct.unpack_from("<I", d, po+16)[0]
                else:
                    po = e_phoff + ph*e_phentsize
                    p_offset = struct.unpack_from("<Q", d, po+8)[0]
                    p_filesz = struct.unpack_from("<Q", d, po+32)[0]
                est = max(est, p_offset + p_filesz)
            arch = {40:"ARM",62:"x86-64",183:"AARCH64",8:"MIPS",3:"x86"}.get(e_machine, "unk(%d)"%e_machine)
            hits.append((i, ei_class*32, arch, e_type, est))
            print("ELF @ 0x%x class=%d arch=%s type=%d est_size=%d" % (i, ei_class*32, arch, e_type, est))
    off = i + 4

print("total ELF candidates:", len(hits))
# save list
import json
json.dump([{"off":o,"bits":b,"arch":a,"type":t,"est":e} for (o,b,a,t,e) in hits],
          open(r"C:\Users\Minhsnguhoa\pmca-re\elf_hits.json","w"), indent=2)
