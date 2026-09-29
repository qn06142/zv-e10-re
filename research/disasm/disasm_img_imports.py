import os, re
from elftools.elf.elffile import ELFFile  # not PE; use pefile-like manual parse instead
UP = (ROOT_REPO / 'fw_update/updater/FirmwareUpdaterImg.dll').as_posix()
data = open(UP,"rb").read()
print("size", len(data))

# This is a PE (not ELF). Parse PE imports + strings manually.
import struct

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
# DOS header
assert data[:2] == b"MZ", "not MZ"
pe_off = struct.unpack_from("<I", data, 0x3c)[0]
print("pe_off", hex(pe_off))
assert data[pe_off:pe_off+2] == b"PE", "not PE"
# COFF header
机器 = struct.unpack_from("<H", data, pe_off+4)[0]
print("machine", hex(机器))
num_sec = struct.unpack_from("<H", data, pe_off+6)[0]
opt_hdr_size = struct.unpack_from("<H", data, pe_off+20)[0]
print("num_sec", num_sec, "opt_hdr_size", opt_hdr_size)
opt_off = pe_off+24
magic = struct.unpack_from("<H", data, opt_off)[0]
print("opt magic", hex(magic), "(0x10b=PE32, 0x20b=PE32+)")
if magic == 0x20b:
    img_base = struct.unpack_from("<Q", data, opt_off+24)[0]
    export_rva = struct.unpack_from("<I", data, opt_off+112)[0]
    export_size = struct.unpack_from("<I", data, opt_off+116)[0]
    import_rva = struct.unpack_from("<I", data, opt_off+120)[0]
    import_size = struct.unpack_from("<I", data, opt_off+124)[0]
else:
    img_base = struct.unpack_from("<I", data, opt_off+28)[0]
    export_rva = struct.unpack_from("<I", data, opt_off+96)[0]
    export_size = struct.unpack_from("<I", data, opt_off+100)[0]
    import_rva = struct.unpack_from("<I", data, opt_off+104)[0]
    import_size = struct.unpack_from("<I", data, opt_off+108)[0]
print("img_base", hex(img_base), "import_rva", hex(import_rva))

# section table
sec_off = opt_off + opt_hdr_size
def rva_to_off(rva):
    for i in range(num_sec):
        o = sec_off + i*40
        name = data[o:o+8]
        vsize = struct.unpack_from("<I", data, o+8)[0]
        vaddr = struct.unpack_from("<I", data, o+12)[0]
        raw = struct.unpack_from("<I", data, o+16)[0]
        if vaddr <= rva < vaddr+vsize:
            return raw + (rva - vaddr)
    return None

# import table
print("\n=== IMPORTS ===")
ioff = rva_to_off(import_rva)
i = 0
while True:
    o = ioff + i*20
    if o+20 > len(data): break
    origfirst = struct.unpack_from("<I", data, o)[0]
    name_rva = struct.unpack_from("<I", data, o+12)[0]
    if name_rva == 0: break
    no = rva_to_off(name_rva)
    if no is None: break
    dllname = data[no:data.index(b"\x00", no)].decode("latin1","replace")
    print("  DLL:", dllname)
    # import lookup / address table (ILT=o, IAT=o+16)
    ilt = struct.unpack_from("<I", data, o+0)[0]  # OriginalFirstThunk
    iat = struct.unpack_from("<I", data, o+16)[0]
    # walk ILT (hint/name entries)
    fth = rva_to_off(ilt) if ilt else rva_to_off(iat)
    names = []
    j = 0
    while fth is not None:
        eoff = fth + j*4
        if eoff+4 > len(data): break
        ent = struct.unpack_from("<I", data, eoff)[0]
        if ent == 0: break
        if ent & 0x80000000:
            names.append("ord%d" % (ent & 0xffff)); j+=1; continue
        hno = rva_to_off(ent)
        if hno is None: break
        # hint(2) + name
        nn = data[hno+2:data.index(b"\x00", hno+2)].decode("latin1","replace")
        names.append(nn); j+=1
    if len(names) > 40:
        print("    (%d funcs, first 40)" % len(names), names[:40])
    else:
        print("    ", names)
    i += 1

# all strings of interest
print("\n=== USB/TRANSPORT/CMD STRINGS ===")
strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{4,}", data)]
seen=set()
for s in strs:
    if re.search(r"USB|Usb|usb|WinUSB|bulk|endpoint|Bulk|transfer|Transfer|send|Send|write|Write|"
                 r"read|Read|request|Request|control|Control|enter|Enter|mode|Mode|update|Update|"
                 r"firm|Firm|Firmware|body|Body|reset|Reset|PID|pid|vid|VID|device|Device|"
                 r"0x|\\|\\\\|pipe|Pipe|stage|Stage|progress|Progress|version|Version|"
                 r"cmd|Cmd|CMD|command|Command|packet|Packet|frame|Frame", s) and s not in seen:
        seen.add(s); print("   ", s)
