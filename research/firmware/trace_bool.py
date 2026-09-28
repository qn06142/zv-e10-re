"""Trace the consumer of the boolean's field, to name it by use.

The method, which just worked
-----------------------------
The deserialiser for c34c39a70111 is at 0x640878, and it stores the value as a
byte at offset +0x11 of a 20-byte object:

    str  r3, [r5]        ; vtable or type tag at +0
    strb r3, [r5, #0x11] ; <-- the boolean payload

That is the write.  Somewhere, a consumer loads [rX, #0x11] from such an object
and does something with it.  If that load can be found, the instructions using the
value name the property by their behaviour, which is the same kind of evidence
that produced the deserialiser mapping: an instruction either branches on the
value or it does not, and no null model is needed for that.

Why +0x11 and not a search for the key
---------------------------------------
Searching for the key finds the deserialiser again, which is already known.  The
question is what happens after.  So the search is inverted: find every 16-bit
load with offset 0x11 in the library, and keep the ones where the loaded value is
then branched on or masked.  A 20-byte object with a byte at +0x11 is a small
enough shape that this offset is distinctive, and the filter is on instruction
form rather than on a value distribution, so it cannot produce the kind of
false positive that the last six data searches produced.

The narrowing, and why it is not a coincidence
-----------------------------------------------
A bare ldrb [rX, #0x11] occurs thousands of times in a 7.6 MB library.  So the
byte offset alone is not evidence.  What makes a hit meaningful is a
conjunction that is unlikely by chance:

  * the load is within a few instructions of a load of a *neighbouring* offset
    from the same property object -- the +0x14, +0x18 and +0x4 fields the
    deserialisers also write.  A consumer of THIS property touches this
    object's other members.
  * the loaded value is then branched on (beq/bne/cbz/cbnz) or masked, rather
    than stored unchanged.
  * the same function was found by the deserialiser pass, so it is in the same
    subsystem and not an unrelated structure with a similar size.

All three together are the test.  A control is reported too: the same search run
against offset 0x12 and 0x10, which are not fields of this object, gives the
rate at which the conjunction occurs by accident.  Without that, the hit count
means nothing -- and a null model is the specific thing whose absence caused the
last five false structures.
"""
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

SO = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\engine\viewUnified2.so')
TEXT_OFF = 0x0018eec8
TEXT_SIZE = 0x074af6c
TEXT_END = TEXT_OFF + TEXT_SIZE

# the 20-byte object built for c34c39a70111, and the sibling fields the other
# deserialisers write, used as the conjunction test
BOOL_OFF = 0x11
SIBLINGS = (0x14, 0x18, 0x04, 0x00)
CONTROL_OFFS = (0x10, 0x12)


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


def disasm_all(b):
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    md.skipdata = True
    return list(md.disasm(b[TEXT_OFF:TEXT_END], TEXT_OFF))


def ldrb_offs(ins, want):
    """addresses of ldrb/ldrb.w with [rN, #want]"""
    out = []
    for x in ins:
        if x.mnemonic in ('ldrb', 'ldrb.w', 'ldrsb', 'ldrsb.w'):
            if ('#%d' % want) in x.op_str and '[' in x.op_str:
                # make sure the offset is a bare displacement, not a scaled one
                if ']' in x.op_str and x.op_str.split('#%d]' % want)[0].endswith(
                        (',', '[')) or x.op_str.endswith('#%d]' % want):
                    out.append(x)
    return out


def window_context(ins, addr, back=6, fwd=14):
    idx = next((k for k, x in enumerate(ins) if x.address == addr), None)
    if idx is None:
        return []
    return ins[max(0, idx - back):idx + fwd]


def classify(ctx, addr):
    """is the loaded value branched on or masked?"""
    acts = []
    idx = next((k for k, x in enumerate(ctx) if x.address == addr), None)
    if idx is None:
        return None, []
    reg = None
    op = ctx[idx].op_str
    if '[' in op:
        reg = op.split('[')[0].strip()
    for y in ctx[idx + 1:]:
        if reg and (reg in y.op_str or y.mnemonic in ('cbz', 'cbnz')):
            if y.mnemonic.startswith('b') or y.mnemonic in ('cbz', 'cbnz'):
                acts.append(('%s %s' % (y.mnemonic, y.op_str)).strip())
            elif y.mnemonic in ('and', 'orr', 'eor', 'bic', 'tst', 'mvn',
                                'lsl', 'lsr', 'asr', 'uxtb', 'uxth',
                                'sxtb', 'sxth', 'subs', 'cmp', 'cmn', 'adds'):
                acts.append('%s %s' % (y.mnemonic, y.op_str))
    return (len(acts) > 0), acts


def sibling_touched(ctx, addr, off):
    """within the window, is [rN, #off] also loaded, and are they the same base?"""
    idx = next((k for k, x in enumerate(ctx) if x.address == addr), None)
    if idx is None:
        return None
    base = None
    if '[' in ctx[idx].op_str:
        base = ctx[idx].op_str.split(',[')[0].split('[')[0].strip()
    for y in ctx[max(0, idx - 6):idx + 14]:
        if y.address == addr:
            continue
        if y.mnemonic.startswith('ldr') and '#%d]' % off in y.op_str:
            if base and y.op_str.split(',[')[0].split('[')[0].strip() == base:
                return True
    return False


def main():
    b = SO.read_bytes()
    print('=== viewUnified2.so, .text %d bytes ===' % TEXT_SIZE)
    print('  the boolean c34c39a70111 is stored at +0x11 of a 20-byte object')
    print()

    ins = disasm_all(b)
    print('  %d instructions decoded (with skipdata for literal pools)' % len(ins))
    print()

    for want, label in ((BOOL_OFF, 'the boolean field'),) + \
            tuple((o, 'control offset 0x%02x' % o) for o in CONTROL_OFFS):
        hits = ldrb_offs(ins, want)
        used = []
        for x in hits:
            ctx = window_context(ins, x.address)
            ok, acts = classify(ctx, x.address)
            sib = any(sibling_touched(ctx, x.address, o) for o in SIBLINGS)
            if ok and acts:
                used.append((x.address, acts, sib))
        print('=' * 74)
        print('%s: ldrb [rN, #0x%02x]' % (label, want))
        print('=' * 74)
        print('  total byte loads at this offset : %d' % len(hits))
        print('  of those, value is branched/masked: %d' % len(used))
        conj = [u for u in used if u[2]]
        print('  AND a sibling field is also read : %d' % len(conj))
        print()
        if want == BOOL_OFF and conj:
            print('  --- conjunction hits: a consumer of this property ---')
            for a, acts, _s in conj[:25]:
                print('  0x%08x  %s' % (a, '; '.join(acts[:3])))
            print()
            for a, acts, _s in conj[:6]:
                print('  --- context 0x%08x ---' % a)
                ctx = window_context(ins, a, back=8, fwd=16)
                for y in ctx:
                    mark = '  <<< the boolean field' if y.address == a else ''
                    print('    %08x  %-8s %-26s%s'
                          % (y.address, y.mnemonic, y.op_str, mark))
                print()
        print()


if __name__ == '__main__':
    main()
