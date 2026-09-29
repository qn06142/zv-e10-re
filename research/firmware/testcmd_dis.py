"""Disassemble libtestcmd.so to recover the test-message file format.

This is the route in.  Unlike av-cam.bin (a raw ORIL blob with no sections),
libtestcmd.so is an ordinary ARM ELF with full section headers, so it can be
disassembled offline with no camera involvement at all.

What the strings already tell us:

    cmdline_read_data_from_file     the message is read from a TEXT file
    cmdline_read_data_from_ibfile   ...or from a BINARY file
    cmdline_read_data_from_args     ...or from command-line arguments
    cmdline_write_data_via_file     responses are written as text
    cmdline_write_bindata_to_stdout
    testcmd_sndmsg / testcmd_rcvmsg  the uipc send/receive
    "%c:0x%x"   "%s:%s"   "0x%02x "   response formats

and the command-line surface from the three .elf front-ends:

    sndcmd.elf --ifile <f> [--ibfile <f>] [--obfile <f>] [--sid <id>] [--sync]
    rcvcmd.elf --ifile <f> [--tmo <ms>] [--sync]
    --sid defaults to 0x00dc0000

So the question is the exact grammar cmdline_read_data_from_file accepts, and
the size/header the message carries.  That is decided by the code, so
disassemble it: find the function, read the fgets/strtoul call sequence, and
recover the field order.
"""
import re
import struct
import sys
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

SO = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\libtestcmd.so')
OUT = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera')

SHT_SYMTAB = 2
SHT_STRTAB = 3
SHT_DYNSYM = 11


def sections(img):
    (e_shoff,) = struct.unpack_from('<I', img, 0x20)
    e_shentsize, e_shnum, e_shstrndx = struct.unpack_from('<HHH', img, 0x2E)
    secs = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        (name, typ, flags, addr, offset, size, link, info, align, entsize) = \
            struct.unpack_from('<10I', img, off)
        secs.append(dict(name=name, type=typ, flags=flags, addr=addr,
                         offset=offset, size=size, link=link, entsize=entsize))
    # resolve names
    shstr = secs[e_shstrndx]
    for s in secs:
        base = shstr['offset'] + s['name']
        end = img.find(b'\x00', base)
        s['sname'] = img[base:end].decode('latin1')
    return secs


def dynsyms(img, secs):
    out = {}
    for s in secs:
        if s['type'] not in (SHT_SYMTAB, SHT_DYNSYM):
            continue
        strtab = secs[s['link']]
        n = s['size'] // 24
        for i in range(n):
            off = s['offset'] + i * 24
            st_name, st_value, st_size, st_info, st_other, st_shndx = \
                struct.unpack_from('<IIIBBH', img, off)
            base = strtab['offset'] + st_name
            end = img.find(b'\x00', base)
            nm = img[base:end].decode('latin1')
            if st_value and nm:
                out[st_value] = (nm, st_size, st_info)
    return out


def main():
    img = SO.read_bytes()
    secs = sections(img)
    print('=== libtestcmd.so sections ===')
    for s in secs:
        if s['sname'] in ('.text', '.rodata', '.dynsym', '.dynstr', '.plt',
                          '.data', '.bss', '.init_array', '.ARM.exidx'):
            print('  %-16s addr 0x%08X off 0x%06X size 0x%05X  type %d'
                  % (s['sname'], s['addr'], s['offset'], s['size'], s['type']))
    syms = dynsyms(img, secs)
    text = next(s for s in secs if s['sname'] == '.text')
    rodata = next(s for s in secs if s['sname'] == '.rodata')
    print()
    print('=== exported/defined functions we care about ===')
    WANT = ('cmdline_read_data_from_file', 'cmdline_read_data_from_ibfile',
            'cmdline_read_data_from_args', 'cmdline_write_data_via_file',
            'cmdline_write_data_via_args', 'testcmd_sndmsg', 'testcmd_rcvmsg',
            'cmdline_init', 'cmdline_get_size', 'cmdline_get_id',
            'cmdline_write_data_to_obfile', 'cmdline_write_bindata_to_stdout',
            'cmdline_read_data_from_args')
    for addr in sorted(syms):
        nm, size, info = syms[addr]
        if nm in WANT:
            kind = 'FUNC' if (info & 0xF) == 2 else 'OTHER'
            print('  0x%08X  %-34s size %5d  %s' % (addr, nm, size, kind))
    print()
    print('=== .rodata strings (formats) ===')
    rb = img[rodata['offset']:rodata['offset'] + rodata['size']]
    for m in re.finditer(rb'[\x20-\x7e]{3,}', rb):
        s = m.group().decode('latin1')
        if any(c in s for c in '%xds:0123456789abcdef') and len(s) < 60:
            print('  ro+0x%04x  (va 0x%08X)  %s'
                  % (m.start(), rodata['addr'] + m.start(), s))


if __name__ == '__main__':
    main()
