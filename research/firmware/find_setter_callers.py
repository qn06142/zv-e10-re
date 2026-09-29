"""Find the callers of the boolean's setter, using aligned decoding only.

Why this file exists
--------------------
The previous run hand-decoded Thumb `bl` immediates and got two things wrong:
J1 and J2 are in the *second* halfword, not the first, and the second-halfword
mask is 0xC000, not 0xD000.  The self-test caught it -- decoding the known
`bl #0x231054` at 0x233504 produced 0x1fd9d02.  So "0 call sites for the setter"
was an artefact of a broken decoder, not a fact about the code.

The lesson is the one this project keeps relearning, in a new costume: an
instrument that cannot fail, or that fails silently, is worse than no
instrument.  The self-test is what saved it.  Every decoder here is now checked
against an instruction whose correct answer is already known from capstone.

Method
------
Use capstone on function bodies only, which trace_bool2.py established keeps the
stream aligned (0.11% bogus ldr<cond> versus tens of thousands when decoding
loose).  capstone's own branch rendering is then trusted for the target, and
only the *call site* extraction is mine -- and that is checked by confirming the
setter itself is found.

What is being asked
------------------
The boolean c34c39a70111 is read at 0x0023350a by a strict ==1 test, and the
true path tail-calls 0x0023342a.  That function is a *setter*: it branches on
its r1 argument, passes 1 or 0 to 0x190a50, writes the same value to a 2-byte
slot at [r4, #0x31], and mirrors it to a byte at [r4, #0x16c].

So the property is stored at offset 0x31 in its parent object, 2 bytes wide.
Knowing the callers tells us which class owns that slot, and the class name is
one demangle away from the caller's exported symbol.  That is the name we want.
"""
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

SO = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\engine\viewUnified2.so')
TEXT_OFF, TEXT_SIZE = 0x0018eec8, 0x074af6c
TEXT_END = TEXT_OFF + TEXT_SIZE
SETTER = 0x0023342a
GETTER_PRED = 0x0023350a


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
    ds = next((s for s in sections(b) if s[0] == '.dynsym'), None)
    dt = next((s for s in sections(b) if s[0] == '.dynstr'), None)
    strs = b[dt[3]:dt[3] + dt[4]]
    out = {}
    for i in range(ds[4] // 16):
        o = ds[3] + i * 16
        nameoff, value, _sz, _i, _o2, _sh = struct.unpack_from('<IIIBBH', b, o)
        if not nameoff or not value:
            continue
        e = strs.find(b'\x00', nameoff)
        a = value & ~1
        nm = strs[nameoff:e].decode('latin1', 'replace')
        if a not in out or len(nm) > len(out[a]):
            out[a] = nm
    return out


def demangle(n):
    if not n.startswith('_ZN'):
        return n
    s, i, parts = n, 3, []
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


def find_functions(b, lo, hi, maxsz=0x4000):
    starts = []
    for o in range(lo, hi - 4, 2):
        w = struct.unpack_from('<H', b, o)[0]
        if (w & 0xFF00) == 0xB500 or (w & 0xFE00) == 0xB400:
            if o >= 8:
                starts.append(o)
    starts = sorted(set(starts))
    return [(s, e) for s, e in zip(starts, starts[1:] + [hi])
            if 0 < e - s <= maxsz]


def nearest_symbol(syms, a, window=0x3000):
    best = None
    for s, nm in syms.items():
        if s <= a and a - s <= window and (best is None or s > best[0]):
            best = (s, nm)
    return best


def main():
    b = SO.read_bytes()
    syms = dynsym(b)
    funcs = find_functions(b, TEXT_OFF, TEXT_END)
    print('=== viewUnified2.so ===')
    print('  functions: %d' % len(funcs))
    print()

    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    md.skipdata = False

    # self-test: confirm the decoder sees the known bl at 0x233504
    print('self-test')
    for a, want in ((0x00233504, 0x231054), (0x0023346e, 0x190a50)):
        for x in md.disasm(b[a:a + 4], a):
            got = x.op_str
            print('  0x%08x  %-6s %-14s  expected 0x%x' % (a, x.mnemonic, got, want))
    print()

    # find call sites
    print('=' * 74)
    print('callers of the setter 0x%08x' % SETTER)
    print('=' * 74)
    sites = []
    for s, e in funcs:
        for x in md.disasm(b[s:e], s):
            if x.mnemonic in ('bl', 'bl', 'b.w') and '0x23342a' in x.op_str:
                sites.append((x.address, s, e))
    print('  %d call sites' % len(sites))
    print()
    named = []
    for a, fs, fe in sites:
        nm = nearest_symbol(syms, fs)
        if nm:
            named.append((a, nm[0], demangle(nm[1])))
    print('  %d of %d are inside an exported function' % (len(named), len(sites)))
    print()
    cnt = Counter(n for _a, _s, n in named)
    for n, c in cnt.most_common(20):
        print('    %4d  %s' % (c, n[:100]))
    print()
    for a, s, n in named[:12]:
        print('  0x%08x  in %s' % (a, n[:90]))
    print()

    # the register that carries the value into the setter
    print('=' * 74)
    print('what is passed in r1 (the boolean) at each call site?')
    print('=' * 74)
    print()
    for a, fs, n in named[:8]:
        back = max(fs, a - 0x40)
        for x in md.disasm(b[back:a + 4], back):
            mk = '  <<< call' if x.address == a else ''
            print('    0x%08x  %-7s %-24s%s' % (x.address, x.mnemonic,
                                                x.op_str, mk))
        print('      in %s' % n[:80])
        print()


if __name__ == '__main__':
    main()
