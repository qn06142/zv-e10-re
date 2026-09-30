"""Recover the test-message format from libtestcmd.so, parsing the ELF properly.

libtestcmd.so is an ordinary ARM EABI shared object (e_type=ET_DYN,
e_machine=EM_ARM, 25 sections at 0x23A8), so unlike av-cam.bin it can be
disassembled offline with no camera involvement.  That makes it the cleanest
route to the uipc test-message interface:

    sndcmd.elf --ifile <file> [--ibfile] [--obfile] [--sid <id>] [--sync]
    rcvcmd.elf --ifile <file> [--tmo <ms>] [--sync]

libtestcmd.so exports the functions that implement those:
    cmdline_read_data_from_file / _ibfile / _args
    cmdline_write_data_via_file / _to_obfile / bindata_to_stdout
    cmdline_get_size / _get_id / _get_sid
    testcmd_sndmsg / testcmd_rcvmsg

An earlier attempt at this produced nonsense because the ELF header fields
were read at the wrong offsets (e_shoff was taken from 0x20 instead of 0x20's
correct sibling, giving e_entry=0x34 and e_type=0x280013).  Both modes then
"disassembled" into garbage that superficially looked plausible.  The header
is fine; the parser was not.
"""
import re
import struct
import pathlib
from pathlib import Path

ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

SO = ROOT_REPO / 'dumps' / 'camera' / 'libtestcmd.so'
img = SO.read_bytes()
md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
md.detail = False

SHT_SYMTAB, SHT_STRTAB, SHT_DYNSYM = 2, 3, 11
SHT_RELA, SHT_JMPREL = 4, 23


class Elf:
    def __init__(self, b):
        self.b = b
        (self.e_type, self.e_machine) = struct.unpack_from('<HH', b, 16)
        (self.e_entry,) = struct.unpack_from('<I', b, 24)
        (self.e_phoff,) = struct.unpack_from('<I', b, 28)
        (self.e_shoff,) = struct.unpack_from('<I', b, 32)
        (self.e_flags,) = struct.unpack_from('<I', b, 36)
        (self.e_ehsize, self.e_phentsize, self.e_phnum,
         self.e_shentsize, self.e_shnum, self.e_shstrndx) = \
            struct.unpack_from('<6H', b, 40)
        self.secs = []
        for i in range(self.e_shnum):
            o = self.e_shoff + i * self.e_shentsize
            name, typ, flags, addr, off, size, link, info, align, entsize = \
                struct.unpack_from('<10I', b, o)
            self.secs.append(dict(idx=i, nameoff=name, type=typ, flags=flags,
                                  addr=addr, offset=off, size=size, link=link,
                                  info=info, align=align, entsize=entsize))
        sh = self.secs[self.e_shstrndx]
        for s in self.secs:
            base = sh['offset'] + s['nameoff']
            s['name'] = b[base:b.find(b'\x00', base)].decode('latin1')

    def sec(self, name):
        for s in self.secs:
            if s['name'] == name:
                return s
        return None

    def dynsyms(self):
        out = {}
        for st in (self.sec('.dynsym'), self.sec('.symtab')):
            if not st:
                continue
            stt = self.secs[st['link']]
            for i in range(st['size'] // st['entsize']):
                o = st['offset'] + i * st['entsize']
                nm, val, size, info, other, shndx = struct.unpack_from('<IIIBBH', self.b, o)
                if not val:
                    continue
                base = stt['offset'] + nm
                name = self.b[base:self.b.find(b'\x00', base)].decode('latin1')
                if name and (val, name) not in out:
                    out[(val, name)] = (size, info & 0xF, st['idx'])
        return out


def main():
    e = Elf(img)
    print('=== ELF32 %s, %d sections ===' %
          ('ET_DYN' if e.e_type == 3 else 'type %d' % e.e_type, e.e_shnum))
    for s in e.secs:
        if s['size']:
            print('  [%2d] %-18s type %-3d addr 0x%08X off 0x%06X size 0x%05X'
                  % (s['idx'], s['name'], s['type'], s['addr'], s['offset'], s['size']))
    print()

    syms = e.dynsyms()
    text = e.sec('.text')
    print('=== functions in .text (0x%08X, 0x%X bytes) ===' % (text['addr'], text['size']))
    fns = sorted((a, n) for (a, n) in syms if n.startswith(('cmdline_', 'testcmd_')))
    for a, n in fns:
        print('  0x%08X  %s' % (a, n))
    print()

    ro = e.sec('.rodata')
    print('=== .rodata strings ===')
    rb = img[ro['offset']:ro['offset'] + ro['size']]
    for m in re.finditer(rb'[\x20-\x7e]{2,}', rb):
        print('  0x%08X  %r' % (ro['addr'] + m.start(), m.group().decode('latin1')))
    print()

    if not text:
        return
    print('=== disassembly of the first text function ===')
    base = text['addr']
    n = 0
    for i in md.disasm(img[text['offset']:text['offset'] + min(text['size'], 160)], base):
        print('  0x%08X  %-10s %-9s %s' % (i.address, i.bytes.hex(' '), i.mnemonic, i.op_str))
        n += 1
        if n > 30:
            break


if __name__ == '__main__':
    main()
