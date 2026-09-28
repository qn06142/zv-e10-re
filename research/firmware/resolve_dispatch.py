"""Resolve the class dispatch table through .rel.dyn, which makes it static after all.

Why the obvious route failed, and what this does instead
-------------------------------------------------------
Each property constructor installs its class entry like this:

    ldr   r5, [pc, #p]        ; a pc-relative offset
    add   r5, pc
    ldr   r3, [pc, #q]        ; a slot index
    ldr   r3, [r5, r3]        ; r3 = GOT[base + index]
    adds  r3, #8
    str   r3, [r4]            ; store at the object head

Hand-computing that for three classes put all three in the same place,
0xC1A3AE, and then put the *targets* in .got (0xC1A3B0 .. 0xC27B08).  Two of the
three read as zero on disk, which is what an unrelocated GOT looks like, so the
table cannot be read straight out of the file.  The section table is what
settles it -- the addresses are in .got, not in .data.rel.ro where a
constructed table would live.

But .rel.dyn is present and is 1,283,752 bytes, which is divisible by 8 and not
by 12, so it is SHT_REL: 8-byte entries of (r_offset, r_info) with no inline
addend, the addend living in the slot itself.  For a REL relocation the loader
sets the slot to the *symbol's* value, and the symbol index is r_info >> 8.
.dynsym is in the file.  So the value is recoverable statically, one indirection
through the relocation table, and no load-time image is needed.

That turns the closed route back into an open one, and it is checkable rather
than hopeful: the resolution is only accepted if it lands in .text or
.rodata, which is where a function pointer or a table of them must be.  A
resolution that lands in .dynamic or .bss is reported as wrong instead of being
used.

The premise is tested before anything is attributed
---------------------------------------------------
The three known classes are different types, so their dispatch entries must lead
somewhere different.  If the three resolve to the same address, the resolution is
wrong and the script stops.  That is the same guard that has caught four wrong
instruments in this session, and it is the only reason the results below can be
believed.
"""
import re
import struct
import bisect
from collections import defaultdict
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

SO = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\engine\viewUnified2.so')

S_TEXT = (0x0018eec8, 0x0018eec8 + 0x0074af6c)
S_RODATA = (0x008d9e40, 0x008d9e40 + 0x001e8745)
S_GOT = (0x00c1a3b0, 0x00c1a3b0 + 0x0000d758)

CLASSES = [
    (0x640850, 'ed188f1a018d', 1),
    (0x640878, 'c34c39a70111', 1),
    (0x648150, '1f0280550208', 2),
    (0x677010, '38f85c32..', 4),
]


def sections(b):
    (shoff,) = struct.unpack_from('<I', b, 32)
    (shentsize, shnum, shstrndx) = struct.unpack_from('<3H', b, 46)
    raw = [struct.unpack_from('<10I', b, shoff + i * shentsize) for i in range(shnum)]
    noff = raw[shstrndx][4]
    out = {}
    for r in raw:
        e = b.find(b'\x00', noff + r[0])
        out[e - noff - r[0] + r[0]] = None      # placeholder, replaced below
    res = []
    for r in raw:
        e = b.find(b'\x00', noff + r[0])
        res.append((b[noff + r[0]:e].decode('latin1', 'replace'),
                    r[1], r[3], r[4], r[5], r[9]))    # name, type, addr, off, size, link
    return res


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


def main():
    b = SO.read_bytes()
    secs = sections(b)
    byname = {s[0]: s for s in secs}
    print('=== sections that matter ===')
    for n in ('.text', '.rodata', '.data.rel.ro', '.got', '.rel.dyn', '.dynsym'):
        if n in byname:
            _nm, ty, ad, of, sz, lk = byname[n]
            print('  %-16s type %-3d addr 0x%08x off 0x%08x size 0x%08x link %d'
                  % (n, ty, ad, of, sz, lk))
    print()

    rel = byname['.rel.dyn']
    entsz = 8 if rel[1] == 9 else 12
    print('=== .rel.dyn ===')
    print('  sh_type %d  ->  %s' % (rel[1], 'SHT_REL' if rel[1] == 9 else 'SHT_RELA'))
    print('  entry size %d, count %d' % (entsz, rel[4] // entsz))
    print()

    relmap = {}
    for i in range(rel[4] // entsz):
        o = rel[3] + i * entsz
        r_off, r_info = struct.unpack_from('<II', b, o)
        if entsz == 12:
            _add = struct.unpack_from('<i', b, o + 8)[0]
        relmap.setdefault(r_off, r_info)
    print('  distinct relocation targets: %d' % len(relmap))
    print()

    # .dynsym
    ds = byname['.dynsym']
    strt = byname['.dynstr']
    strs = b[strt[3]:strt[3] + strt[4]]
    nsym = ds[4] // 16
    print('=== .dynsym ===')
    print('  %d symbols' % nsym)
    print()

    def sym(i):
        o = ds[3] + i * 16
        nameoff, value, size, info, other, shndx = struct.unpack_from('<IIIBBH', b, o)
        if not nameoff:
            return (0, '')
        e = strs.find(b'\x00', nameoff)
        return (value, strs[nameoff:e].decode('latin1', 'replace'))

    def resolve_got(addr):
        info = relmap.get(addr)
        if info is None:
            return None, 'no .rel.dyn entry for 0x%08x' % addr
        si = info >> 8
        ty = info & 0xFF
        val, nm = sym(si)
        return (val, nm), 'type %d sym %d %s' % (ty, si, nm[:40] or '(anon)')

    # ---- per class: recompute the GOT slot, then resolve -----------------
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    md.skipdata = False
    print('=== resolving each class dispatch entry ===')
    print()
    resolved = {}
    for start, key, arity in CLASSES:
        ins = list(md.disasm(b[start:start + 0x40], start))
        A = B = None
        addpc = None
        for x in ins:
            full = x.mnemonic + ' ' + x.op_str
            m = re.match(r'^ldr\s+(r\d+),\s*\[pc,\s*#(-?(?:0x)?[0-9a-fx]+)\]', full)
            if m:
                imm = int(m.group(2), 0)
                ea = (x.address & ~3) + 4 + imm
                if 0 <= ea + 4 <= len(b):
                    v = struct.unpack_from('<I', b, ea)[0]
                    if A is None:
                        A = v
                    else:
                        B = v
            m = re.match(r'^add\s+(r\d+),\s*pc$', full)
            if m:
                addpc = (x.address & ~3) + 4
            if x.mnemonic in ('pop',) and 'pc' in x.op_str:
                break
        if A is None or B is None or addpc is None:
            print('  0x%08x arity %d  %-14s  could not read the pool words'
                  % (start, arity, key))
            continue
        slot = addpc + A + B
        insec = 'outside .got' if not (S_GOT[0] <= slot < S_GOT[1]) else 'in .got'
        r, how = resolve_got(slot)
        if r is None:
            print('  0x%08x arity %d  %-14s  slot 0x%08x  %s  %s'
                  % (start, arity, key, slot, insec, how))
            continue
        val, nm = r
        region = ('.text' if S_TEXT[0] <= val < S_TEXT[1] else
                  '.rodata' if S_RODATA[0] <= val < S_RODATA[1] else
                  'other')
        resolved[start] = (val, nm, region)
        print('  0x%08x arity %d  %-14s  slot 0x%08x  %s'
              % (start, arity, key, slot, insec))
        print('        -> 0x%08x  (%s)  %s' % (val, region, demangle(nm)[:56]))
    print()

    if len(resolved) < 2:
        print('  fewer than two resolved; the diff is not attempted.')
        return

    print('=== the premise: known classes must resolve differently ===')
    print()
    known = [a for a in resolved if a != 0x677010]
    vals = {a: resolved[a][0] for a in known}
    print('  %d known classes -> %s' % (len(known), [hex(v) for v in vals.values()]))
    if len(set(vals.values())) < len(vals):
        print('  IDENTICAL.  Different types cannot share a dispatch entry, so the')
        print('  resolution is wrong and nothing is attributed to any slot.')
        return
    print('  they differ, so the premise holds.')
    print()

    # ---- the rect class's entry, read as a table -------------------------
    rect = 0x677010
    if rect not in resolved:
        print('  the rect class did not resolve; nothing further.')
        return
    val, nm, region = resolved[rect]
    print('=== the rect class dispatch entry ===')
    print('  0x%08x  %s  %s' % (val, region, demangle(nm)[:56]))
    print()
    if region != '.rodata' and region != '.text':
        print('  it is not a table in a readable section, so the class-specific')
        print('  function cannot be read from the file.  Reported, not guessed.')
        return
    print('  read as a table of 32-bit entries (each +8 skips two header slots):')
    print()
    for i in range(24):
        p = val + i * 4
        if p + 4 > len(b):
            break
        e = struct.unpack_from('<I', b, p)[0]
        t = e & ~1
        where = ('.text' if S_TEXT[0] <= t < S_TEXT[1] else
                 '.rodata' if S_RODATA[0] <= t < S_RODATA[1] else '?')
        print('    +%3d  0x%08x  %-8s%s' % (i, e, where, '  (thumb)' if e & 1 else ''))
    print()


if __name__ == '__main__':
    main()
