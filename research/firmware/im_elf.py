"""Parse im.elf -- the imaging daemon, and the process that owns the uipc bus.

/etc/uipc_stat_kernel.txt (1860 lines, pulled from the camera) shows only two
processes on the message bus:

    Process 157   msgqs 417   sems 134   cbs 310   <-- /proc/157/comm = im.elf
    Process 149   msgqs 0     sems 0     cbs 0     <-- bootin.elf (idle)

So im.elf is the service that receives display commands, and the UI engine
maps its /dev/uipc: in uxengine_res2's maps there is

    04673000-04773000 rw-s 09800000 /dev/uipc      1 MB

im.elf is an ordinary ARM ELF in /usr/bin (23,240 B), so unlike av-cam.bin it
parses and disassembles offline.  Two things to establish:

  1. the real section layout and whether it is Thumb or ARM
  2. the uipc message-id dispatch table, i.e. which ids im.elf handles and
     which of them are display commands

The id table is the missing piece for the testcmd route: sndcmd.elf needs an
osal_id, and the default 0x00dc0000 is a *source* id.  If im.elf's dispatch
switch can be read, the display command ids fall out of it.

Lessons that matter here, both learned the hard way on libtestcmd.so:
  * header fields must be read at their correct offsets or the output is
    plausible-looking fiction (e_type=0x280013, unnamed PLT stubs)
  * function symbols carry the Thumb bit, so ARM-mode disassembly is garbage
    that does not look like an error
"""
import re
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

ELF = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\im.elf')
img = ELF.read_bytes()

SHT_SYMTAB, SHT_STRTAB, SHT_DYNSYM = 2, 3, 11


class Elf:
    def __init__(self, b):
        self.b = b
        assert b[:4] == b'\x7fELF', 'not an ELF'
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
        for st in (self.sec('.dynsym'), self.sec('.symtab')):
            if not st:
                continue
            stt = self.secs[st['link']]
            for i in range(st['size'] // st['entsize']):
                o = st['offset'] + i * st['entsize']
                nm, val, size, info, other, shndx = struct.unpack_from('<IIIBBH', self.b, o)
                if not val or not nm:
                    continue
                base = stt['offset'] + nm
                name = self.b[base:self.b.find(b'\x00', base)].decode('latin1')
                thumb = bool(val & 1)
                key = (val & ~1, name)
                if key not in out or (size and not out[key][0]):
                    out[key] = (size, info & 0xF, thumb, st['idx'])
        return out


def main():
    e = Elf(img)
    print('=== im.elf: %d bytes, %s, machine %d, entry 0x%08X ==='
          % (len(img), {2: 'EXEC', 3: 'DYN'}.get(e.e_type, e.e_type),
             e.e_machine, e.e_entry))
    print('  e_flags 0x%08X   sections %d at 0x%X'
          % (e.e_flags, e.e_shnum, e.e_shoff))
    print('  EF_ARM_HASENTRY(0x2)=%s  EF_ARM_INTERWORK(0x4)=%s'
          % (bool(e.e_flags & 2), bool(e.e_flags & 4)))
    print()
    for s in e.secs:
        if s['size']:
            print('  [%2d] %-18s type %-11d addr 0x%08X off 0x%06X size 0x%05X'
                  % (s['idx'], s['name'], s['type'], s['addr'], s['offset'], s['size']))
    print()

    syms = e.symbols()
    fns = sorted((a, n, v) for (a, n), v in syms.items() if v[1] == 2)
    print('=== %d function symbols ===' % len(fns))
    thumb = sum(1 for _, _, v in fns if v[2])
    print('  %d carry the Thumb bit' % thumb)
    for a, n, v in fns[:60]:
        print('  0x%08X %-6s %5d  %s'
              % (a, 'THUMB' if v[2] else 'ARM', v[0], n))
    if len(fns) > 60:
        print('  ... and %d more' % (len(fns) - 60))
    print()

    # which ISA actually decodes cleanly at the first function?
    text = e.sec('.text')
    if text and fns:
        va = fns[0][0]
        off = text['offset'] + (va - text['addr'])
        for mode, name in ((CS_MODE_THUMB, 'THUMB'), (CS_MODE_ARM, 'ARM')):
            md = Cs(CS_ARCH_ARM, mode | CS_MODE_LITTLE_ENDIAN)
            ins = list(md.disasm(img[off:off + 24], va))
            txt = '; '.join('%s %s' % (i.mnemonic, i.op_str) for i in ins[:5])
            print('  %-6s decode of 0x%08X: %s' % (name, va, txt))
    print()

    # strings worth reading
    for sn in ('.rodata', '.dynstr'):
        s = e.sec(sn)
        if not s:
            continue
        print('=== %s interesting strings ===' % sn)
        blob = img[s['offset']:s['offset'] + s['size']]
        pat = re.compile(rb'[\x20-\x7e]{5,}')
        keep = []
        total = 0
        for m in pat.finditer(blob):
            total += 1
            t = m.group().decode('latin1')
            if re.search(r'uipc|osal|msg|cmd|display|panel|vdf|draw|osd|testcmd|'
                         r'qid|queue|CMD|ID_|IMDB|imdb', t, re.I):
                keep.append((s['addr'] + m.start(), t))
        for a, t in keep[:80]:
            print('  0x%08X  %s' % (a, t[:100]))
        print('  (%d of %d strings matched)' % (len(keep), total))


if __name__ == '__main__':
    main()
