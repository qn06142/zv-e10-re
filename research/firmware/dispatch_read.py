"""Read the property dispatch at 0x670ddc and name the fields from behaviour.

Where this is
-------------
F1/F2 recovered 48,612 function starts in viewUnified2.so's .text (median body
34 bytes, p90 180) and found 244 functions that load a property key from a Thumb
literal pool, of which 122 dispatch on 3 or more distinct properties.  They are
unexported, so the symbol table cannot help; the code has to be read.

0x00670ddc is the richest: five keys, including both layout properties
(1b572204, 1f028055), the boolean (c34c39a7) and two 16-bit-value properties
(0fcbce25, ed188f1a).  A function handling that set is almost certainly one
widget class's property reader.

What to extract, and why each is evidence rather than guesswork
--------------------------------------------------------------
D1  The key comparison chain.  Each property is dispatched by loading the key
    from the pool, comparing, and branching to a handler.  Recovering the branch
    targets gives the per-property handler addresses, which is the skeleton of
    the class.

D2  Within each handler, the payload read.  A handler that does
    `ldrb rX, [rBase, #2]` is reading payload byte 2 of that property.  Since
    the resource-file layout is known -- signature is 6 bytes, payload starts
    at +6 -- payload byte 2 of 1f0280550208 is file offset +8, and payload byte 0
    is +6.  That connects the code to the exact bytes a patch would touch, which
    is the thing the whole exercise has been missing.

D3  What the value is used for.  A value loaded and then masked is a flags
    field.  Compared against 0 and 1 is a boolean.  Used as an index into a
    table is an enumeration.  Stored unchanged into a struct is a plain value.
    Each of those is a name, derived from an instruction rather than from a
    value distribution, so it does not need a null model -- an instruction
    either masks or it does not.

D4  The falsification.  If the handlers turn out to be a single shared helper
    called with different offsets, then the per-property handlers are not
    distinct and the "one widget class" reading is wrong.  Checking whether the
    branch targets are distinct catches that.

Address arithmetic on Thumb
---------------------------
    ldr  rX, [pc, #imm]  ->  address = (PC & ~3) + 4 + imm,  PC = insn + 4
    b.w  target          ->  target = insn + 4 + (sign_extend(imm24) << 2)
    b<cc> target         ->  target = insn + 4 + (sign_extend(imm11) << 1)
    cbz/cbnz             ->  16-bit, imm 9 bits, target = insn + 4 + imm*2

All are computed from the raw instruction words rather than read from capstone
where possible, because a wrong PC base is exactly the kind of error that
produces plausible nonsense.  Both are cross-checked: the computed target must
land inside .text.
"""
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

SO = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\engine\viewUnified2.so')

PROP_KEYS = {
    0x0422571b: ('1b572204010e', 6, 10),   # sig, payload_off, payload_len
    0x5580021f: ('1f0280550208', 6, 9),
    0xa7394cc3: ('c34c39a70111', 6, 1),
    0x0fcbce25: ('0fcbce250190', 6, 2),
    0x1a8f18ed: ('ed188f1a018d', 6, 2),
    0x905a43e0: ('e0435a90018d', 6, 2),
    0x62b3c38a: ('8ac3b3620202', 6, 9),
    0xbfad4621: ('2146adbf018d', 6, 2),
    0x410d7649: ('49760d41018d', 6, 2),
    0x6c0acfdb: ('dbcf0a6c018d', 6, 2),
}
TARGETS = [
    (0x00670ddc, 'richest: 5 keys'),
    (0x00648178, '4 keys'),
    (0x0064939a, '4 keys'),
    (0x0066e2d8, '4 keys'),
    (0x0066ff60, '4 keys + 0fcbce25'),
]


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


def sx(v, bits):
    m = 1 << (bits - 1)
    return (v ^ m) - m


def decode_16(b, a, lo, hi):
    """Return (mnemonic, target) for branches, else (mnemonic, None)."""
    w = struct.unpack_from('<H', b, a)[0]
    top = w >> 12
    if top == 0xD and (w & 0x0F00) == 0x0F00:      # b.w
        op = (w >> 14) & 3
        s = (w >> 10) & 1
        imm11 = w & 0x7FF
        j1 = (w >> 13) & 1
        j2 = (w >> 11) & 1
        i1 = 1 - (j1 ^ s)
        i2 = 1 - (j2 ^ s)
        imm = (s << 24) | (i1 << 23) | (i2 << 22) | (imm11 << 1)
        imm = sx(imm, 25)
        cond = ['eq', 'ne', 'cs', 'cc', 'mi', 'pl', 'vs', 'vc',
                'hi', 'ls', 'ge', 'lt', 'gt', 'le', 'al', ''][op]
        return 'b%s' % cond, a + 4 + imm
    if top in (0, 1) and (w & 0xF000) == (0xD000 & 0xF000):
        pass
    if 0xE000 <= w <= 0xE7FF:                     # b<cond> 11-bit
        op = (w >> 8) & 0xF
        imm = sx(w & 0xFF, 8)
        cond = ['eq', 'ne', 'cs', 'cc', 'mi', 'pl', 'vs', 'vc',
                'hi', 'ls', 'ge', 'lt', 'gt', 'le', '', 'nv'][op]
        return 'b%s' % cond, a + 4 + (imm << 1)
    return None, None


def ldr_pc_target(b, a):
    """For a 16-bit ldr rX,[pc,#imm], return the pool address."""
    w = struct.unpack_from('<H', b, a)[0]
    if (w & 0xF800) != 0x4800:
        return None
    imm = (w & 0xFF) * 4
    pc = (a + 4) & ~3
    return pc + imm


def analyse(b, lo, hi, start, note):
    print('=' * 78)
    print('function 0x%08x  -- %s' % (start, note))
    print('=' * 78)
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    size = min(0x3000, hi - start)
    code = b[start:start + size]
    ins = list(md.disasm(code, start))
    print('  %d instructions decoded' % len(ins))
    print()

    # D1: find every key load and the branch that follows it
    print('  --- key dispatches ---')
    handlers = {}
    for i, x in enumerate(ins):
        if x.mnemonic != 'ldr':
            continue
        tgt = ldr_pc_target(b, x.address)
        if tgt is None or not (lo <= tgt < hi):
            continue
        v = struct.unpack_from('<I', b, tgt)[0]
        if v not in PROP_KEYS:
            continue
        sig, poff, plen = PROP_KEYS[v]
        reg = x.op_str.split(',')[0].strip()
        # look ahead for a compare on that register and a branch
        br = None
        cmp_at = None
        for y in ins[i + 1:i + 12]:
            if y.mnemonic in ('cmp', 'cmn') and reg in y.op_str:
                cmp_at = y.address
            if cmp_at is not None and y.mnemonic.startswith('b'):
                br = (y.address, y.op_str)
                break
        # raw decode as a cross-check
        raw_br = None
        if cmp_at is not None:
            for y in ins[i + 1:i + 12]:
                if y.address > cmp_at:
                    _m, t = decode_16(b, y.address, lo, hi)
                    if t is not None:
                        raw_br = t
                    break
        t = br[1] if br else ''
        tt = raw_br
        handlers[sig] = (tt, t)
        print('    0x%08x  ldr %s,[pc] -> key 0x%08x  %-16s payload+%d len %d'
              % (x.address, reg, v, sig, poff, plen))
        if tt is not None and (lo <= tt < hi):
            print('        handler @0x%08x  %s' % (tt, t))
        elif br:
            print('        branch mnemonic %s (target not in .text?)' % br[1])
    print()
    uniq = set(h for h, _ in handlers.values() if h)
    print('  %d distinct handler targets across %d dispatches'
          % (len(uniq), len(handlers)))
    print('  D4: %s' % ('handlers are distinct -> one class reader'
                        if len(uniq) >= max(1, len(handlers) - 1) else
                        'handlers COLLAPSE -> shared helper, not a class reader'))
    print()

    # D2/D3: payload reads per handler
    for sig, (ht, _) in handlers.items():
        if ht is None:
            continue
        # find the instruction index at the handler
        idx = next((k for k, x in enumerate(ins) if x.address == ht), None)
        if idx is None:
            print('  %-16s handler 0x%08x not in decoded window' % (sig, ht))
            continue
        print('  --- %-16s handler @0x%08x ---' % (sig, ht))
        shown = 0
        for y in ins[idx:idx + 26]:
            if y.address > ht + 120:
                break
            note = ''
            if y.mnemonic in ('ldrb', 'ldrh', 'ldr') and '[' in y.op_str:
                m = re_imm(y.op_str)
                if m is not None:
                    note = '  <- reads payload byte %d' % m
            elif y.mnemonic in ('and', 'bic', 'tst', 'lsl', 'lsr', 'asr',
                                'uxtb', 'uxth', 'sxtb', 'sxth'):
                note = '  <- bit manipulation'
            elif y.mnemonic == 'cmp':
                note = '  <- compared against'
            print('      %08x  %-7s %-26s%s' % (y.address, y.mnemonic,
                                                y.op_str, note))
            shown += 1
            if shown > 18:
                break
        print()


def re_imm(op):
    m = op.rfind('#')
    if m < 0:
        return None
    s = op[m + 1:].rstrip(']!')
    try:
        return int(s, 0)
    except ValueError:
        return None


def main():
    import re
    b = SO.read_bytes()
    text = next(s for s in sections(b) if s[0] == '.text')
    lo, hi = text[3], text[3] + text[4]
    print('=== viewUnified2.so, .text 0x%08x..0x%08x ===' % (lo, hi))
    print()
    for start, note in TARGETS:
        analyse(b, lo, hi, start, note)
        print()


if __name__ == '__main__':
    import re
    globals()['re'] = re
    main()
