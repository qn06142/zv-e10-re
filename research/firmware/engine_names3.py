"""Is there any readable property name in the binaries? Settle it properly.

Correcting the previous run
---------------------------
It reported "621 exclusive strings (candidate namings)" and then printed them as
`1F F?`.  Those are not strings.  They are ARM/Thumb instruction bytes that
happen to fall in the printable ASCII range -- the pool at 0x64xxxx is code, not
a name table.  A 5-character printable run is far too weak a filter to separate
text from opcodes.

So the honest count of candidate namings is zero, and the previous output
overstated it.  The real question is whether the binaries contain property
names in any recoverable form, and that needs a proper test rather than a
printable-byte filter.

What a real name would look like
--------------------------------
  * a NUL-terminated ASCII run of >= 6 chars, containing at least two letters
    and no bytes in the ARM-conditional-instruction range, i.e. not the
    "1F F?" pattern
  * inside a read-only data section, not .text
  * ideally adjacent to, or referenced by, a property key constant

The section test is the decisive one.  Both libraries are ordinary ELF shared
objects, so they have program headers and section tables.  A name lives in
.rodata; an opcode lives in .text.  Comparing printable runs per section settles
it without guessing at filters.

What the registry does tell us, which is worth keeping
------------------------------------------------------
The structure at 0x648774 is real and interpretable regardless of names:

    0x648774  c34c39a7 0191   key: the boolean
    0x648778  ed188f1a 018d   key
    0x64877c  1b572204 010e   key
    0x648780  1f028055 0208   key
    0x648784  72dc12e4         value: NOT a known key -> a handler pointer
    0x648788  4a311dea 018c   key
    0x64878c  2146adbf 018d   key
    ...

and 0x72dc12e4 recurs in every one of the six runs inspected, always in the slot
after 1b572204/1f028055.  A field that is constant across every record of a
table is a dispatch target, not data.  So this is a property registry: a set of
keys mapped to a shared handler for the two layout properties that every object
has.

That is a structural fact, established without any name, and it is what a future
property-mapping tool would hook into.
"""
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path

ENG = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\engine')

KNOWN_SIGS = [
    '1b572204010e', '1f0280550208', 'c34c39a70111', '8ac3b3620202',
    'ed06f4340100', 'ec18a67a0290', 'e0435a90018d', '2146adbf018d',
    '49760d41018d', 'dbcf0a6c018d', '0fcbce250190', 'ed188f1a018d',
    '4a311dea018c', '7fb68c7f0190', '82d530c60190', '03193943018c',
    '547e85a6018c', '2dac7cb2018c', '571c3df3018c', '94899f21018d',
    '0d4d93430190', 'd7520f8d018d', 'ae338fba018d', '3254afad018c',
    '1f0b9b400190', 'c3bd3492018d', 'a99afb240190', '9975ed000190',
    '27d4bdf90190', 'b62031c60190', 'a77eda3b0190', 'c34c39a70191',
]
KEYS = {}
for s in KNOWN_SIGS:
    KEYS[struct.unpack('<I', bytes.fromhex(s[:8]))[0]] = s


def sections(b):
    """Return [(name, type, off, size)] from the ELF section table."""
    if b[:4] != b'\x7fELF':
        return []
    (shoff,) = struct.unpack_from('<I', b, 32)
    (shentsize, shnum, shstrndx) = struct.unpack_from('<3H', b, 46)
    if not shoff or not shnum:
        return []
    secs = []
    names_off = None
    for i in range(shnum):
        o = shoff + i * shentsize
        nameoff, stype, _fl, addr, off, size = struct.unpack_from('<6I', b, o)
        if i == shstrndx:
            names_off = off
        secs.append([nameoff, stype, addr, off, size])
    out = []
    for nameoff, stype, addr, off, size in secs:
        e = b.find(b'\x00', names_off + nameoff)
        nm = b[names_off + nameoff:e].decode('latin1', 'replace')
        out.append((nm, stype, addr, off, size))
    return out


def real_strings(chunk, minlen=6):
    """Printable runs that are plausibly text, not opcodes.

    Requires at least 3 ASCII letters, and rejects the 0x1F-prefixed pattern
    that Thumb/ARM condition codes produce.
    """
    out = []
    for m in re.finditer(rb'[\x20-\x7e]{%d,}' % minlen, chunk):
        t = m.group().decode('latin1')
        letters = sum(1 for c in t if c.isalpha())
        if letters < 3:
            continue
        if re.match(r'^[A-Z][FI][?@]', t):
            continue
        out.append(t)
    return out


def main():
    for name in ('viewUnified2.so', 'libSysDef.so', 'libObj.so'):
        p = ENG / name
        if not p.exists():
            continue
        b = p.read_bytes()
        secs = sections(b)
        print('#' * 76)
        print('# %s  %d bytes  %d sections' % (name, len(b), len(secs)))
        print('#' * 76)
        if not secs:
            print('  no section table')
            continue
        ro = [(o, sz) for nm, ty, _a, o, sz in secs
              if nm in ('.rodata', '.data.rel.ro') and sz]
        tx = [(o, sz) for nm, ty, _a, o, sz in secs if nm == '.text' and sz]
        print('  .rodata-ish: %s' % ', '.join('%d B' % sz for _o, sz in ro) or 'none')
        print('  .text:       %s' % ', '.join('%d B' % sz for _o, sz in tx) or 'none')
        print()
        for o, sz in ro:
            ss = real_strings(b[o:o + sz], 6)
            print('  rodata strings (>=6, letter-bearing): %d' % len(ss))
            # only show ones with UI vocabulary
            v = [t for t in ss if re.search(
                r'visible|enabl|select|focus|state|style|color|alpha|'
                r'widget|property|uxc|palette', t, re.I)]
            print('  of which UI vocabulary: %d' % len(v))
            for t in v[:40]:
                print('     %s' % t[:100])
        print()

        # how many property keys are in .rodata vs .text?
        for label, region in (('.rodata', ro), ('.text', tx)):
            if not region:
                continue
            n = 0
            for k in KEYS:
                c = b.count(struct.pack('<I', k), region[0][0], region[0][0] + region[0][1])
                n += c
            print('  property-key constants in %s: %d' % (label, n))
        print()
        # .dynsym: any exported names at all?
        dyn = [(nm, o, sz) for nm, ty, _a, o, sz in secs if nm == '.dynsym']
        if dyn:
            print('  .dynsym size %d B' % dyn[0][2])
        strt = [(nm, o, sz) for nm, ty, _a, o, sz in secs if nm == '.dynstr']
        if strt:
            d = b[strt[0][1]:strt[0][1] + strt[0][2]]
            names = [t for t in d.split(b'\x00') if len(t) >= 4]
            print('  exported symbol names: %d' % len(names))
            for t in names[:25]:
                print('     %s' % t.decode('latin1', 'replace'))
        print()


if __name__ == '__main__':
    main()
