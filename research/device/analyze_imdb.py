import struct
from elftools.elf.elffile import ELFFile

with open('F:/D/lib/libIMDB.so', 'rb') as f:
    elf = ELFFile(f)
    rodata = elf.get_section_by_name('.rodata')
    rodata_base = rodata['sh_addr']
    rodata_data = rodata.data()

    relro = elf.get_section_by_name('.data.rel.ro')
    relro_base = relro['sh_addr']
    relro_data = relro.data()

    def get_str(addr):
        if addr == 0:
            return ''
        if rodata_base <= addr < rodata_base + len(rodata_data):
            off = addr - rodata_base
            end = rodata_data.find(b'\x00', off)
            return rodata_data[off:end].decode('ascii', errors='replace')
        return f'<addr:0x{addr:x}>'

    # Entry 3 onwards where type == 1 has IMDB:name
    # Let's inspect all entries where type == 1:
    entry_sz = 44
    num_entries = len(relro_data) // entry_sz
    for i in range(num_entries):
        chunk = relro_data[i*entry_sz : (i+1)*entry_sz]
        type_, target, flag, me, psid, f_ptr = struct.unpack('<LLLHH L', chunk[:20])
        if type_ == 1 or 'IMDB:' in get_str(f_ptr):
            print(f'Bit {i-3 if i>=3 else i}: type={hex(type_)} target={hex(target)} str="{get_str(f_ptr)}"')
