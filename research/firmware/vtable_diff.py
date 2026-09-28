"""Resolve the vtable of each property class and diff the slots.

The situation
-------------
A census of the whole engine finds the four-field payload shape exactly once, at
constructor 0x677010, and finds no four-field *reader*.  Three explanations, and
they are distinguishable:

  (a) the reader is in another library (viewUnified6.so, libObj.so, libSysDef.so);
  (b) the four fields are filled by four separate callers, one each;
  (c) the reader writes them in a form this detector cannot see -- a block copy,
      stmia, or a vector store.

The vtable settles it, because a property class is polymorphic and the read is
almost certainly a virtual.  Every constructor here installs its vtable the same
way, so the vtable address is computable rather than searched for, and the slots
can be compared across classes that are known to differ.

Computing the vtable
--------------------
The install sequence in all of them is:

    ldr   r5, [pc, #p1]     ; a pc-relative offset
    ...
    ldr   r3, [pc, #p2]     ; a second one
    add   r5, pc            ; r5 = pc + A          (Thumb: Align(PC,4) = addr+4)
    ldr   r3, [r5, r3]      ; r3 = *(r5 + B)
    adds  r3, #8            ; skip the two header slots
    str   r3, [r4]          ; store at the object head

so vtable = *(Align(addr_of_add, 4) + A + B) + 8, where A and B are the two
literal-pool words.  Worked by hand for 0x677010 and then checked against the
three known classes, whose vtables must differ from each other somewhere or the
classes would be interchangeable.

Why the diff is the answer rather than a step towards one
--------------------------------------------------------
Four classes, four vtables.  If the classes are genuinely different types, the
vtable layouts must differ -- otherwise the engine could not tell them apart at
all.  So a slot that differs across the known three identifies, by position, the
slot that carries type-specific behaviour.  The arity-4 class's entry in that
same slot is then its reader, and reading it gives the on-disk encoding of four
consecutive values.

Falsifiable at every step
------------------------
  * if the three known classes' vtables are identical, the premise is wrong and
    the script says so rather than continuing;
  * if the arity-4 vtable cannot be resolved, that is reported, not guessed;
  * if the differing slot holds a pointer outside .text, it is not a function and
    is reported as such.
"""
import re
import struct
import bisect
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

SO = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\engine\viewUnified2.so')
TEXT_OFF, TEXT_SIZE = 0x0018eec8, 0x074af6c
TEXT_END = TEXT_OFF + TEXT_SIZE

CLASSES = [
    (0x640850, 'ed188f1a018d', 1),
    (0x640878, 'c34c39a70111', 1, 'bool'),
    (0x648150, '1f0280550208', 2),
    (0x677010, '38f85c32..    ', 4, 'THE RECT'),
]
SLOTS = 40


def demangle(n):
    if not n.startswith('_ZN'):
        return n
    i, p = 3, []
    while i < len(n):
        m = re.match(r'(\d+)', n[i:])
        if not m:
            break
        ln = int(m.group(1))
        i += len(m.group(1))
        p.append(n[i:i + ln])
        i += ln
        if i < len(n) and n[i] == 'E':
            break
    return '::'.join(p) if p else n


def dynsym(b):
    (shoff,) = struct.unpack_from('<I', b, 32)
    (shentsize, shnum, shstrndx) = struct.unpack_from('<3H', b, 46)
    raw = [struct.unpack_from('<6I', b, shoff + i * shentsize) for i in range(shnum)]
    noff = raw[shstrndx][4]

    def nm(r):
        e = b.find(b'\x00', noff + r[0])
        return b[noff + r[0]:e]
    ds = next(r for r in raw if nm(r) == b'.dynsym')
    dt = next(r for r in raw if nm(r) == b'.dynstr')
    strs = b[dt[4]:dt[4] + dt[5]]
    out = {}
    for i in range(ds[5] // 16):
        o = ds[4] + i * 16
        n2, val, _z, _i, _o2, _sh = struct.unpack_from('<IIIBBH', b, o)
        if not n2 or not val:
            continue
        e = strs.find(b'\x00', n2)
        a, s = val & ~1, strs[n2:e].decode('latin1', 'replace')
        if a not in out or len(s) > len(out[a]):
            out[a] = s
    return out


def pool(b, insn_addr, op_str):
    m = re.search(r'\[pc,\s*#(-?(?:0x)?[0-9a-fx]+)\]', op_str)
    if not m:
        return None
    a = (insn_addr & ~3) + 4 + int(m.group(1), 0)
    if not (0 <= a + 4 <= len(b)):
        return None
    return struct.unpack_from('<I', b, a)[0]


def resolve(b, start, md):
    """follow the vtable-install idiom; return (vtable_addr, how) or (None, why)"""
    ins = list(md.disasm(b[start:start + 0x40], start))
    A = B = None
    addpc = None
    for x in ins:
        full = x.mnemonic + ' ' + x.op_str
        m = re.match(r'^ldr\s+(r\d+),\s*\[pc,', full)
        if m and m.group(1) in ('r4', 'r5', 'r6', 'r7'):
            v = pool(b, x.address, x.op_str)
            if A is None:
                A = v
            else:
                B = v
        m = re.match(r'^add\s+(r\d+),\s*pc$', full)
        if m:
            addpc = (x.address & ~3) + 4
        m = re.match(r'^ldr\s+(r\d+),\s*\[(r\d+),\s*(r\d+)\]$', full)
        if m and addpc is not None and A is not None and B is not None:
            dst, base, idx = m.group(1), m.group(2), m.group(3)
            if pool(b, x.address, x.op_str) is None and '[pc' not in x.op_str:
                addr = addpc + A + B
                if not (0 <= addr + 4 <= len(b)):
                    return None, 'vtable slot address 0x%x out of range' % addr
                vt = struct.unpack_from('<I', b, addr)[0]
                return vt + 8, 'pool A=0x%x B=0x%x' % (A, B)
    return None, 'idiom not found (A=%s B=%s addpc=%s)' % (A, B, addpc)


def main():
    b = SO.read_bytes()
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    md.skipdata = False
    syms = dynsym(b)
    saddr = sorted(syms)

    def near(a):
        j = bisect.bisect_right(saddr, a) - 1
        return demangle(syms[saddr[j]]) if j >= 0 else '(unexported)'

    print('=== resolving each class vtable ===')
    print()
    vts = {}
    for c in CLASSES:
        a, key, arity = c[0], c[1], c[2]
        note = c[3] if len(c) > 3 else ''
        vt, how = resolve(b, a, md)
        vts[a] = vt
        print('  0x%08x  arity %d  %-14s %-10s -> %s'
              % (a, arity, key, note,
                 ('vtable 0x%08x   [%s]' % (vt, how)) if vt else 'FAILED: ' + how))
    print()

    good = {a: v for a, v in vts.items() if v}
    if len(good) < 2:
        print('  fewer than two vtables resolved; nothing to diff.')
        return

    print('=== the vtable contents ===')
    print()
    tabs = {}
    for a, vt in good.items():
        row = []
        for i in range(SLOTS):
            p = vt + i * 4
            row.append(struct.unpack_from('<I', b, p)[0] if p + 4 <= len(b) else 0)
        tabs[a] = row
    hdr = '  slot  ' + '  '.join('0x%08x' % a for a in sorted(tabs))
    print(hdr)
    for i in range(SLOTS):
        vals = [tabs[a][i] for a in sorted(tabs)]
        uniq = len(set(vals)) > 1
        mark = '  <-- differs' if uniq else ''
        print('  %4d  %s%s' % (i, '  '.join('0x%08x' % v for v in vals), mark))
    print()

    # ---- is the premise sound?  known classes must differ -----------------
    known = [a for a in tabs if a != 0x677010]
    print('=== C: the known classes must not be identical ===')
    print()
    diffslots = []
    for i in range(SLOTS):
        vals = {tabs[a][i] for a in known}
        if len(vals) > 1:
            diffslots.append(i)
    print('  slots where the %d known classes differ: %s'
          % (len(known), diffslots if diffslots else 'NONE'))
    if not diffslots:
        print()
        print('  The three known classes have identical vtables over %d slots.' % SLOTS)
        print('  That cannot be right -- they are different types, and the engine')
        print('  has to tell them apart.  So the vtable resolution is wrong, and no')
        print('  slot may be attributed to type-specific behaviour.')
        return
    print('  premise holds: the classes are distinguishable, so differing slots')
    print('  carry the class-specific behaviour.')
    print()

    print('=== the type-specific slots, and what the rect class has there ===')
    print()
    for i in diffslots:
        vals = {a: tabs[a][i] for a in tabs}
        targets = {v & ~1 for v in vals.values()}
        intext = all(TEXT_OFF <= t < TEXT_END for t in targets)
        print('  slot %-3d  %s   %s'
              % (i, '  '.join('0x%08x->0x%08x' % (a, vals[a] & ~1) for a in sorted(vals)),
                 'all in .text' if intext else 'NOT all in .text'))
        for a in sorted(vals):
            t = vals[a] & ~1
            if TEXT_OFF <= t < TEXT_END:
                ar = next((c[2] for c in CLASSES if c[0] == a), '?')
                print('        arity %-2s 0x%08x  in %s' % (ar, t, near(t)[:52]))
    print()

    # ---- dump the rect class's type-specific function ---------------------
    rect = 0x677010
    if rect in tabs:
        for i in diffslots:
            t = tabs[rect][i] & ~1
            if not (TEXT_OFF <= t < TEXT_END):
                continue
            print('=' * 78)
            print('RECT CLASS, slot %d -> 0x%08x   in %s' % (i, t, near(t)[:48]))
            print('=' * 78)
            n = 0
            for x in md.disasm(b[t:t + 0x100], t):
                print('  %08x  %-8s %-26s' % (x.address, x.mnemonic, x.op_str))
                n += 1
                if x.mnemonic in ('pop', 'bx') and 'pc' in x.op_str:
                    break
                if n > 60:
                    print('  ... (truncated)')
                    break
            print()
            break


if __name__ == '__main__':
    main()
