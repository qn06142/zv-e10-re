"""Disassemble stream.ko / stream2.ko -- a user-mappable kernel buffer.

Why this is interesting now
---------------------------
The ldec display driver is compiled into the kernel (its /proc/modules entry is
10,106 bytes with the (P) "statically allocated core" flag, and no ldec.ko
exists on disk), so its code cannot be read as a file.  But the two /dev/stream
drivers are ordinary relocatable modules that came off the filesystem, and each
exports:

    stream.ko    stream_mmap  128 B    stream_ioctl  128 B
    stream2.ko   stream_mmap  320 B    stream_ioctl  316 B

A `mmap` in a character driver is a userspace-visible kernel buffer: if any of
these devices maps a frame or display surface, then a program of our own can
write pixels into it directly and the panel will show them.  That is the one
route to a visible effect that does not require guessing a message id or an
ioctl struct, and it is exactly the shape of a legitimate firmware API -- the
driver itself hands out the pointer.

So: read both modules, find the mmap handler, and answer three questions.

  1. What does stream_mmap actually map?  (vm_ops->fault, a vmalloc, a
     remap_pfn_range of a DMA buffer, a bounce buffer)
  2. What is the size/geometry the driver enforces?  Any width/height/stride
     field recovered here is the pixel layout we would write.
  3. What are stream_ioctl's commands?  Small-int dispatch, same shape as
     ldec_ioctl (established: cmd 1 -> -EIO, cmd 2 -> -EFAULT).

Both modules are ARM (machine 40) and their symbols carry no Thumb bit, so the
functions are ARM mode.  .text is mapped 1:1 from file offset 0x34 with
addr 0, so a symbol's value is its offset into .text.
"""
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

KO = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera')


class Elf:
    def __init__(self, b):
        self.b = b
        assert b[:4] == b'\x7fELF', 'not an ELF'
        (self.e_type, self.e_machine) = struct.unpack_from('<HH', b, 16)
        (self.e_shoff,) = struct.unpack_from('<I', b, 32)
        (self.e_flags,) = struct.unpack_from('<I', b, 36)
        (self.e_shentsize, self.e_shnum, self.e_shstrndx) = \
            struct.unpack_from('<3H', b, 46)
        self.secs = []
        for i in range(self.e_shnum):
            o = self.e_shoff + i * self.e_shentsize
            v = struct.unpack_from('<10I', b, o)
            self.secs.append(dict(idx=i, nameoff=v[0], type=v[1], flags=v[2],
                                  addr=v[3], offset=v[4], size=v[5], link=v[6],
                                  info=v[7], align=v[8], entsize=v[9]))
        sh = self.secs[self.e_shstrndx]
        for s in self.secs:
            base = sh['offset'] + s['nameoff']
            s['name'] = b[base:b.find(b'\x00', base)].decode('latin1')

    def sec(self, n):
        for s in self.secs:
            if s['name'] == n:
                return s

    def symbols(self):
        out = {}
        for st in (self.sec('.symtab'), self.sec('.dynsym')):
            if not st:
                continue
            stt = self.secs[st['link']]
            for i in range(st['size'] // st['entsize']):
                o = st['offset'] + i * st['entsize']
                nm, val, size, info, other, shndx = struct.unpack_from('<IIIBBH', self.b, o)
                if not nm:
                    continue
                base = stt['offset'] + nm
                name = self.b[base:self.b.find(b'\x00', base)].decode('latin1')
                out[name] = (val & ~1, size, info & 0xF, bool(val & 1))
        return out

    def off(self, va, secname):
        s = self.sec(secname)
        return s['offset'] + (va - s['addr'])


def disasm(e, img, va, size, label):
    text = e.sec('.text')
    off = text['offset'] + (va - text['addr'])
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
    md.detail = False
    print('\n--- %s  (0x%06X, %d bytes) ---' % (label, va, size))
    for i in md.disasm(img[off:off + size], va):
        print('  %08X  %-8s %s' % (i.address, i.mnemonic, i.op_str))


def rostrings(e, img, pat=None):
    s = e.sec('.rodata')
    if not s:
        return
    blob = img[s['offset']:s['offset'] + s['size']]
    print('  .rodata %d bytes:' % s['size'])
    for m in __import__('re').finditer(rb'[\x20-\x7e]{3,}', blob):
        t = m.group().decode('latin1')
        if pat is None or pat in t:
            print('    0x%08X  %s' % (s['addr'] + m.start(), t))


def main():
    import re
    for name in ('ko_stream.ko', 'ko_stream2.ko'):
        p = KO / name
        img = p.read_bytes()
        e = Elf(img)
        syms = e.symbols()
        print('=' * 78)
        print('=== %s  %d bytes  e_type %d  flags 0x%08X' % (name, len(img), e.e_type, e.e_flags))
        print('  modinfo:')
        mi = e.sec('.modinfo')
        if mi:
            for m in re.finditer(rb'[\x20-\x7e]{3,}', img[mi['offset']:mi['offset'] + mi['size']]):
                print('    %s' % m.group().decode('latin1'))
        print('  .rodata:')
        rostrings(e, img)
        print('  .data (%d bytes):' % e.sec('.data')['size'])
        d = e.sec('.data')
        for i in range(0, d['size'], 16):
            chunk = img[d['offset'] + i:d['offset'] + i + 16]
            print('    0x%06X  %s' % (i, chunk.hex(' ')))
        print('  functions:')
        for fn, (v, sz, ty, th) in sorted(syms.items(), key=lambda kv: kv[1][0]):
            if ty == 2 and sz:
                print('    %-24s 0x%06X %5d %s' % (fn[:24], v, sz, 'THUMB' if th else 'ARM'))
        for fn in ('stream_mmap', 'stream_ioctl', 'stream_open',
                   'stream_release', 'stream_read', 'stream_write', 'fops'):
            if fn in syms:
                v, sz, ty, th = syms[fn]
                if sz and v + sz <= e.sec('.text')['size']:
                    mode = 'THUMB' if th else 'ARM'
                    text = e.sec('.text')
                    off = text['offset'] + (v - text['addr'])
                    n = sz if sz < 700 else 700
                    print('\n  == disasm %s (%s, %d bytes) ==' % (fn, mode, sz))
                    m2 = Cs(CS_ARCH_ARM, (CS_MODE_THUMB if th else CS_MODE_ARM) | CS_MODE_LITTLE_ENDIAN)
                    for i in m2.disasm(img[off:off + n], v):
                        print('    %08X  %-8s %s' % (i.address, i.mnemonic, i.op_str))
                else:
                    print('\n  %s: val 0x%06X size %d (not in .text)' % (fn, v, sz))


if __name__ == '__main__':
    main()
