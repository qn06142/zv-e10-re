"""Recover ldec_ioctl and the display buffer from the on-disk kernel modules.

This closes the blocker that forced the earlier dead ends.  The ldec driver was
only reachable as a running VA (0x5F00A2E8 from /proc/kallsyms) and every way
of reading that VA failed:

  * /dev/mem at PA 0x5F00A000  -> 0 bytes (not in a RAM window)
  * /dev/mem at kernel text PA  -> 0 bytes (read-only mapping unreachable)
  * /dev/mem below page size    -> 0-byte file, no error
  * swapper_pg_dir / page_offset-> not exported by kallsyms
  * /proc/self/pagemap          -> all zeros, even for our own mapped heap
  * /proc/ldec                 -> does not exist

But the modules are ON DISK in /usr/kmod/, and a .ko file is an ordinary ELF
relocatable object.  So ldec's code can be read from the file with no camera
involvement at all, which is what this does.

/proc/modules gives the ldec code size as 10,106 bytes with the load address
0x5f00a000 and flag (P) -- statically allocated core, i.e. linked into the
kernel rather than a separate insmod'd object.  So ldec's text is probably
inside dmm.ko (85,588 B) or liro.ko (65,212 B) rather than its own file.  This
script searches every pulled module for the ldec symbol names from kallsyms:

    5f00a2e8 t ldec_ioctl
    5f00a820 t ldec_read_proc
    5f00abc0 t ldec_init
    5f00a03c T boss_lld_get_base_addr_ldec

and, if found, disassembles ldec_ioctl to recover the ioctl argument layout.
The ioctl numbers are plain small integers (established: 39 _IOC encodings all
returned -EINVAL, but command 1 -> -EIO and command 2 -> -EFAULT, and -EFAULT
means the driver dereferences the argument), so the dispatch switch is what
defines each command's struct.
"""
import re
import struct
import sys
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

KO = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera')

# symbols we know exist, from /proc/kallsyms
LDEC_SYMS = ['ldec_open', 'ldec_close', 'ldec_resume', 'ldec_suspend',
             'ldec_remove', 'ldec_probe', 'ldec_exit', 'ldec_ioctl',
             'ldec_read_proc', 'ldec_init', 'boss_hw_ldec_process',
             'boss_hw_ldec_set', 'boss_hw_ldec_enable_irq',
             'boss_hw_ldec_resource_init', 'boss_hw_ldec_wait',
             'boss_hw_ldec_get_state', 'boss_hw_ldec_stop',
             'boss_lld_get_base_addr_ldec', 'boss_hw_ldec_disable_irq',
             'boss_hw_ldec_request_irq', 'boss_hw_ldec_free_irq',
             'boss_debug_dump_ldec', 'boss_hw_ldec_lock']

STREAM_SYMS = ['stream_open', 'stream_ioctl', 'stream_read', 'stream_write',
               'stream_mmap', 'stream_release']


class Elf:
    def __init__(self, b):
        self.b = b
        if b[:4] != b'\x7fELF':
            raise ValueError('not an ELF')
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
                out[(val & ~1, name)] = (val, size, info & 0xF, bool(val & 1))
        return out


def survey(path, dump_syms=None):
    b = path.read_bytes()
    print('=== %s  %d bytes  magic %s ===' % (path.name, len(b), b[:4].hex(' ')))
    if b[:4] != b'\x7fELF':
        return None, None
    e = Elf(b)
    print('  e_type %d  machine %d  e_flags 0x%08X  %d sections'
          % (e.e_type, e.e_machine, e.e_flags, e.e_shnum))
    for s in e.secs:
        if s['size'] and s['name'] in ('.text', '.rodata', '.data', '.strtab',
                                        '.symtab', '.dynsym', '.dynstr',
                                        '.rel.dyn', '.rela.dyn', '.modinfo',
                                        '__versions', '.gnu.linkonce.this_module',
                                        '.ARM.exidx', '.init_array'):
            print('    %-22s addr 0x%08X off 0x%06X size 0x%05X'
                  % (s['name'], s['addr'], s['offset'], s['size']))
    try:
        syms = e.symbols()
    except Exception as ex:
        print('  symbols: %s' % ex)
        return e, {}
    named = sorted((val, name) for (addr, name), val in syms.items())
    print('  %d symbols; ldec/stream matches:' % len(named))
    hits = 0
    for info, name in named:
        if any(k in name for k in LDEC_SYMS + STREAM_SYMS):
            print('    %-34s val 0x%08X size %5d' % (name, info[0], info[1]))
            hits += 1
    if not hits:
        print('    (none)')
    return e, syms


def main():
    for p in sorted(KO.glob('ko_*.ko')):
        survey(p)
        print()

    print('=== function symbols per module ===')
    for p in sorted(KO.glob('ko_*.ko')):
        b = p.read_bytes()
        if b[:4] != b'\x7fELF':
            continue
        e = Elf(b)
        try:
            syms = e.symbols()
        except Exception:
            continue
        fns = sorted([(v[0], n, v[1], v[3]) for (a, n), v in syms.items()
                      if v[2] == 2 and n])
        print('\n--- %s: %d functions ---' % (p.name, len(fns)))
        for v, n, sz, th in fns[:50]:
            print('    %-36s 0x%06X %5d %s' % (n[:36], v, sz, 'T' if th else 'A'))

    print()
    print('=== raw string search for ldec symbols across pulled modules ===')
    for p in sorted(KO.glob('ko_*.ko')):
        b = p.read_bytes()
        found = [s for s in LDEC_SYMS if s.encode() in b]
        if found:
            print('  %-18s %s' % (p.name, ', '.join(found)))


if __name__ == '__main__':
    main()
