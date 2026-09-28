"""Mine libIMDB.so for the uipc command table: name -> id.

Why this file matters
--------------------
sndcmd.elf needs an `osal_id`, and its default 0x00dc0000 is a *source* id,
not a display command.  The missing piece has been "which id reaches the
display", and /etc/uipc_stat_kernel.txt shows the bus carries 857 message
queues but names none of them.

im.elf (the imaging daemon, pid 157, which owns 417 of those queues) links
against libIMDB.so and calls:

    IMDB_find_entry        look a command up by name
    IMDB_get_entries       enumerate the table
    IMDB_find_target_bit

so libIMDB.so *is* the command database: name -> id.  If its table is a
static array in .data or .rodata, the whole map is readable offline with no
camera at all.  And libIMDB.so is an ordinary ARM ELF (37,044 B), so it
parses and disassembles normally.

Two decoding traps already paid for once on libtestcmd.so, so re-checked here
rather than assumed:
  * ELF header fields must be read at their correct offsets
  * symbol values carry the Thumb bit, so pick the mode from the symbols

The expected shape: pairs (const char *name, uint32 id) in a table, with a
count.  Look for a .data/.rodata region where 32-bit words look like plausible
uipc ids (high byte nonzero, as in 0x00dc____) and are interleaved with pointers
into .rodata that resolve to printable names.
"""
import re
import struct
from pathlib import Path

SO = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\libIMDB.so')
img = SO.read_bytes()
SHT_SYMTAB, SHT_STRTAB, SHT_DYNSYM = 2, 3, 11


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
                out[(val & ~1, name)] = (size, info & 0xF, bool(val & 1))
        return out


e = Elf(img)
print('=== libIMDB.so: %d bytes, %s, machine %d, %d sections ==='
      % (len(img), {2: 'EXEC', 3: 'DYN'}.get(e.e_type, e.e_type), e.e_machine, e.e_shnum))
for s in e.secs:
    if s['size']:
        print('  [%2d] %-18s addr 0x%08X off 0x%06X size 0x%05X'
              % (s['idx'], s['name'], s['addr'], s['offset'], s['size']))
print()

syms = e.symbols()
fns = sorted((a, n) for (a, n), v in syms.items() if v[1] == 2)
print('=== %d function symbols ===' % len(fns))
for a, n in fns[:40]:
    print('  0x%08X %-6s %s' % (a, 'THUMB' if syms[(a, n)][2] else 'ARM', n))
print()

ro = e.sec('.rodata')
print('=== .rodata: %d bytes, all strings ===' % ro['size'])
blob = img[ro['offset']:ro['offset'] + ro['size']]
strs = [(ro['addr'] + m.start(), m.group().decode('latin1'))
        for m in re.finditer(rb'[\x20-\x7e]{3,}', blob)]
for a, t in strs[:120]:
    print('  0x%08X  %s' % (a, t[:90]))
print('  ... %d strings total' % len(strs))
print()

# Look for a (ptr, id) table in .data or .rodata
print('=== scanning for a (name-pointer, uipc-id) table ===')
SECS = {s['name']: s for s in e.secs}


def va_to_off(va):
    for s in e.secs:
        if s['addr'] and s['addr'] <= va < s['addr'] + s['size']:
            return s['offset'] + (va - s['addr']), s['name']
    return None, None


def looks_like_uipc_id(v):
    # 0x00dc____ style ids seen in the bus stats / --sid default
    return (v & 0xFFFF0000) in (0x00DC0000, 0x00DE0000, 0x00D00000) or \
           (0x1000 < v < 0x10000 and (v & 0xFF) == 0)


found = {}
for sname in ('.data', '.rodata'):
    s = SECS.get(sname)
    if not s:
        continue
    for off in range(s['offset'], s['offset'] + s['size'] - 8, 4):
        p, v = struct.unpack_from('<II', img, off)
        po, pn = va_to_off(p)
        if po is None or pn not in ('.rodata', '.dynstr', '.data'):
            continue
        txt = img[po:img.find(b'\x00', po)].decode('latin1')
        if len(txt) < 3 or not all(32 <= ord(c) < 127 for c in txt):
            continue
        found.setdefault(sname, []).append((s['addr'] + (off - s['offset']), p, v, txt))

for sname, rows in found.items():
    print('\n--- candidates in %s: %d ---' % (sname, len(rows)))
    for va, p, v, txt in rows[:60]:
        print('  table@0x%08X  name@0x%08X %-34s  id=0x%08X' % (va, p, txt[:34], v))
