"""Disassemble the consumer of 1f0280550208 and name it from the code.

Why code, not data
-----------------
Six structures in this project looked real and were not, and five of them came
from a data filter that could not fail.  The fix each time was a null model or a
control.  This is the method that has not failed yet, because a disassembly is
not a filter: it either shows the instruction that consumes the field or it does
not.

The target
----------
1f0280550208 is the second most common property in the corpus, 9,562 instances,
and its +2 field has 240 distinct values up to 644.  Whatever that field is, it
is a per-object parameter with a curated value set, and the code that reads it
will say what it is.

How to find the consumer
------------------------
The keys live in viewUnified2.so as Thumb literal-pool immediates: 549
occurrences of 0x5502801f.  Each is loaded by an ldr from a pc-relative pool and
compared against the incoming property key.  So the consumer is the function
containing that ldr, and the interesting instruction is the one that reads the
payload byte at the offset the comparison is gating.

Concretely, for each occurrence of the key in .text:
  * decode backwards and forwards as Thumb to find the enclosing function
  * find the ldr that references the pool entry
  * look for a subsequent load of [base, #imm] where imm corresponds to payload
    offset 2 -- that is the field being read
  * report the surrounding instructions, which name the field by what it is
    compared against, stored into, or used as an index

Realistically, the highest-value first step is not the full dataflow.  It is
naming the surrounding symbols: viewUnified2.so exports 4,181 dynamic symbols,
so a function at a given address can be attributed to a class and method name.
If the consumer of this property is, say, ux::wgtsys::LayoutConverter::convert,
that alone says the property belongs to layout conversion, and the geometry
question answers itself.

That is the cheap, high-information step, and it comes first.

Addressing
----------
The pool offsets are file offsets.  .text is mapped 1:1 in this library (section
addr == offset for .text at 0x0010fee0), so a Thumb function address and a file
offset coincide.  Symbol values from .dynsym are already Thumb-masked, so both
the masked and unmasked forms are tried when attributing an address.

What this does not do
---------------------
It does not claim a property is geometry.  It reports what the code does with
it, which is a fact, and lets the reading follow from that rather than from a
value distribution.
"""
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path

from capstone import (Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_ARM,
                      CS_MODE_LITTLE_ENDIAN)

ENG = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\engine')
SO = ENG / 'viewUnified2.so'

def key_of(sig_hex8):
    """u32 from the literal on-disk signature bytes, little-endian.

    The signature is written as key[4] then tag[2], and the on-disk bytes for
    1f0280550208 are 1f 02 80 55 02 08, so the key bytes are 1f 02 80 55 and
    the little-endian u32 is 0x5580021f.  Reading the hex string as a number
    instead of as bytes gives 0x5502801f, which appears nowhere -- that mistake
    cost one run and produced a false '0 occurrences'.
    """
    return struct.unpack('<I', bytes.fromhex(sig_hex8))[0]


PROP_KEY = key_of('1f028055')      # 1f0280550208  -> 0x5580021f
PROP_KEY_B = key_of('1b572204')    # 1b572204010e  -> 0x0422571b
BOOL_KEY = key_of('c34c39a7')      # c34c39a70191  -> 0xa7394cc3


def sections(b):
    (shoff,) = struct.unpack_from('<I', b, 32)
    (shentsize, shnum, shstrndx) = struct.unpack_from('<3H', b, 46)
    raw = [struct.unpack_from('<6I', b, shoff + i * shentsize)
           for i in range(shnum)]
    noff = raw[shstrndx][4]
    out = []
    for nameoff, stype, _fl, addr, off, size in raw:
        e = b.find(b'\x00', noff + nameoff)
        out.append((b[noff + nameoff:e].decode('latin1', 'replace'),
                    stype, addr, off, size))
    return out


def dynsym(b):
    secs = sections(b)
    ds = next((s for s in secs if s[0] == '.dynsym'), None)
    dt = next((s for s in secs if s[0] == '.dynstr'), None)
    if not ds or not dt:
        return {}
    strs = b[dt[3]:dt[3] + dt[4]]
    out = defaultdict(list)
    for i in range(ds[4] // 16):
        o = ds[3] + i * 16
        nameoff, value, _sz, _i, _o2, _sh = struct.unpack_from('<IIIBBH', b, o)
        if not nameoff or not value:
            continue
        e = strs.find(b'\x00', nameoff)
        nm = strs[nameoff:e].decode('latin1', 'replace')
        out[value & ~1].append(nm)
    return out


def demangle(n):
    if not n.startswith('_ZN'):
        return n
    s = n
    i = 3
    parts = []
    while i < len(s):
        m = re.match(r'(\d+)', s[i:])
        if not m:
            break
        ln = int(m.group(1))
        i += len(m.group(1))
        parts.append(s[i:i + ln])
        i += ln
        if i < len(s) and s[i] == 'E':
            break
    return '::'.join(parts) if parts else n


def find_key(b, key, lo, hi):
    pat = struct.pack('<I', key)
    out = []
    i = lo
    while True:
        i = b.find(pat, i, hi)
        if i < 0:
            return out
        out.append(i)
        i += 1


def enclosing_symbol(syms, addr):
    """Largest dynamic symbol at or below addr, within a sane distance."""
    best = None
    for a, names in syms.items():
        if a <= addr and (addr - a) < 0x2000:
            if best is None or a > best[0]:
                best = (a, names[0])
    return best


def disasm_at(b, addr, n=40, backward=32):
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    start = max(0, addr - backward)
    code = b[start:addr + n * 4]
    return list(md.disasm(code, start))


def main():
    b = SO.read_bytes()
    syms = dynsym(b)
    secs = sections(b)
    text = next((s for s in secs if s[0] == '.text'), None)
    ro = next((s for s in secs if s[0] == '.rodata'), None)
    print('=== viewUnified2.so ===')
    print('  .text  off 0x%08x size 0x%07x  (addr==off: %s)'
          % (text[3], text[4], text[2] == text[3]))
    print('  .rodata off 0x%08x size 0x%07x' % (ro[3], ro[4]))
    print('  dynamic symbols: %d' % len(syms))
    print()

    for name, key in (('1f0280550208', PROP_KEY),
                      ('1b572204010e', PROP_KEY_B),
                      ('c34c39a70191 (boolean)', BOOL_KEY)):
        print('=' * 78)
        print('%s  -- key 0x%08x' % (name, key))
        print('=' * 78)
        hits = find_key(b, key, text[3], text[3] + text[4])
        print('  %d occurrences inside .text' % len(hits))
        if not hits:
            print('  none in .text; checking whole file')
            hits = find_key(b, key, 0, len(b))
            print('  %d in whole file' % len(hits))
        print()
        # attribute a sample to symbols
        named = 0
        sample = []
        for h in hits:
            s = enclosing_symbol(syms, h)
            if s:
                named += 1
                sample.append((h, s[0], demangle(s[1])))
        print('  %d of %d fall within 0x2000 of an exported symbol'
              % (named, len(hits)))
        print()
        cnt = Counter(n for _h, _a, n in sample)
        for n, c in cnt.most_common(14):
            print('    %4d  %s' % (c, n[:96]))
        print()

        # disassemble the two densest sites
        if sample:
            print('  --- disassembly at the first few sites ---')
            for h, sa, sn in sample[:3]:
                print()
                print('  site 0x%08x, in %s (symbol 0x%08x)' % (h, sn[:70], sa))
                for i in disasm_at(b, h, n=14, backward=24):
                    mark = '  <-- key pool entry' if i.address <= h < i.address + i.size else ''
                    print('    %08x  %-7s %-28s%s'
                          % (i.address, i.mnemonic, i.op_str, mark))
            print()

    # The decisive question: is the boolean's consumer named?
    print('=' * 78)
    print('which class consumes the boolean property?')
    print('=' * 78)
    print()
    hits = find_key(b, BOOL_KEY, text[3], text[3] + text[4])
    named = []
    for h in hits:
        s = enclosing_symbol(syms, h)
        if s:
            named.append((h, s[0], demangle(s[1])))
    cnt = Counter(n for _h, _a, n in named)
    print('  %d of %d boolean-key sites are near an exported symbol' % (len(named), len(hits)))
    print()
    for n, c in cnt.most_common(20):
        print('    %4d  %s' % (c, n[:100]))
    print()
    if cnt:
        top = cnt.most_common(1)[0]
        print('  dominant consumer of the boolean: %s (%d sites)' % (top[0][:90], top[1]))


if __name__ == '__main__':
    main()
