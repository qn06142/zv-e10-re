import os, re, struct
UP = r"C:\Users\Minhsnguhoa\pmca-re\fw_update\updater"

def parse_pe(path):
    data = open(path,"rb").read()
    print("=== %s (%d bytes) ===" % (os.path.basename(path), len(data)))
    assert data[:2]==b"MZ"
    pe_off = struct.unpack_from("<I", data, 0x3c)[0]
    assert data[pe_off:pe_off+2]==b"PE"
    机器 = struct.unpack_from("<H", data, pe_off+4)[0]
    num_sec = struct.unpack_from("<H", data, pe_off+6)[0]
    opt_hdr_size = struct.unpack_from("<H", data, pe_off+20)[0]
    opt_off = pe_off+24
    magic = struct.unpack_from("<H", data, opt_off)[0]
    is64 = magic==0x20b
    if is64:
        img_base = struct.unpack_from("<Q", data, opt_off+24)[0]
        import_rva = struct.unpack_from("<I", data, opt_off+120)[0]
    else:
        img_base = struct.unpack_from("<I", data, opt_off+28)[0]
        import_rva = struct.unpack_from("<I", data, opt_off+104)[0]
    print("machine", hex(机器), "img_base", hex(img_base), "import_rva", hex(import_rva))

    sec_off = opt_off + opt_hdr_size
    def rva_to_off(rva):
        for i in range(num_sec):
            o = sec_off + i*40
            vsize = struct.unpack_from("<I", data, o+8)[0]
            vaddr = struct.unpack_from("<I", data, o+12)[0]
            raw = struct.unpack_from("<I", data, o+16)[0]
            if vaddr <= rva < vaddr+vsize:
                return raw + (rva - vaddr)
        return None

    print("\n--- IMPORTS (DLL : funcs) ---")
    ioff = rva_to_off(import_rva)
    i = 0
    while True:
        o = ioff + i*20
        if o+20 > len(data): break
        ilt = struct.unpack_from("<I", data, o+0)[0]
        name_rva = struct.unpack_from("<I", data, o+12)[0]
        if name_rva == 0: break
        no = rva_to_off(name_rva)
        if no is None: break
        end = data.index(b"\x00", no)
        dllname = data[no:end].decode("latin1","replace")
        fth = rva_to_off(ilt) if ilt else None
        names=[]
        if fth is not None:
            j=0
            while True:
                eoff = fth + j*4
                if eoff+4 > len(data): break
                ent = struct.unpack_from("<I", data, eoff)[0]
                if ent == 0: break
                if ent & 0x80000000:
                    names.append("ord%d"%(ent&0xffff)); j+=1; continue
                hno = rva_to_off(ent)
                if hno is None: break
                nn = data[hno+2:data.index(b"\x00", hno+2)].decode("latin1","replace")
                names.append(nn); j+=1
        # dedupe
        uniq = list(dict.fromkeys(names))
        if len(uniq) > 50:
            print("  %s (%d): %s ..." % (dllname, len(uniq), ", ".join(uniq[:50])))
        else:
            print("  %s: %s" % (dllname, ", ".join(uniq)))
        i += 1

    print("\n--- USB/UPDATE/COMMAND-RELATED STRINGS ---")
    strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{4,}", data)]
    seen=set()
    for s in strs:
        if re.search(r"WinUSB|WinUsb|Usb|USB|bulk|endpoint|Endpoint|Bulk|control|Control|"
                     r"CreateFile|\\\\\.\\\\|setupapi|SetupDi|Hid|hid|transfer|Transfer|"
                     r"enter|Enter|update|Update|firm|Firm|Firmware|body|Body|mode|Mode|"
                     r"\\x5c|\\\\|0x[0-9a-fA-F]{2,}|pid|PID|vid|VID|request|Request|"
                     r"send|Send|write|Write|read|Read|packet|Packet|cmd|Cmd|CMD|stage|Stage|"
                     r"progress|Progress|version|Version|reset|Reset|0x5", s, re.I) and s not in seen:
            seen.add(s); print("   ", s)

for fn in ("FirmwareUpdaterEg.exe","FirmwareUpdaterImg.dll"):
    parse_pe(os.path.join(UP, fn))
    print()
