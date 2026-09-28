"""Find the READER for the four-field class: the function that fills 0x14..0x20.

The position, and why this is the next thing
--------------------------------------------
The constructor at 0x677010 is known: it zeroes four consecutive words at
0x14/0x18/0x1c/0x20 and owns exactly one key.  That identifies the *class*.  It
says nothing about how the four values are encoded in the file, which is the
only thing that matters for editing them.  The class must have a partner that
fills those same four fields from the byte stream, and that partner is the
answer: it is the only place in the binary where the on-disk encoding of a
four-field property is written down.

Scanning the files cannot substitute.  The key's 37 occurrences turned out to be
35 byte-identical, so they are declarations, and the values are not adjacent.
Six previous geometry searches each had a scoring rule that could not fail; this
one has a target the engine itself specifies.

How the two halves are told apart
---------------------------------
Both constructors and readers write the same four offsets, so the payload shape
alone does not separate them.  Two independent signals do:

  * Constructors call the shared base constructor 0x1872c8.  Readers do not --
    they are handed a live object and only fill fields.
  * Readers consume the stream.  The stream arrives as a register that is walked
    and offset, and the values come back from a call.  A constructor never does
    that, because it has no stream yet.

Neither is trusted alone.  A function is reported as a reader candidate only if
it has the four-field shape AND lacks the base-constructor call, and the count of
each group is printed so an asymmetric result is visible.

Calibration
-----------
The same detector, run over the three known classes, must find their constructors
and must not report them as readers.  If a known constructor turns up in the
reader list, the split is wrong and the candidates are not printed.
"""
import re
import struct
import bisect
from collections import Counter, defaultdict
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

SO = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\engine\viewUnified2.so')
TEXT_OFF, TEXT_SIZE = 0x0018eec8, 0x074af6c
TEXT_END = TEXT_OFF + TEXT_SIZE
BASE_CTOR = 0x1872c8
HDR = 0x10

KNOWN_CTORS = {
    0x640850: 'ed188f1a018d  arity 1',
    0x640878: 'c34c39a70111  arity 1 (bool)',
    0x648150: '1f0280550208  arity 2',
}
TARGET_CTOR = 0x677010          # the arity-4 class


def find_functions(b, lo, hi, maxsz=0x2000):
    starts = []
    for o in range(lo, hi - 4, 2):
        w = struct.unpack_from('<H', b, o)[0]
        if (w & 0xFF00) == 0xB500 or (w & 0xFE00) == 0xB400:
            if o >= 8:
                starts.append(o)
    starts = sorted(set(starts))
    return [(s, e) for s, e in zip(starts, starts[1:] + [hi])
            if 0 < e - s <= maxsz]


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


def payload_fields(ins):
    """{field offset: width} for stores of provably-zero or freshly-read values.

    Two zero-regimes are accepted, because a constructor zeroes and a reader
    stores what it just read, and both write the same shape:
      * the stored register was set to zero a few instructions back, or
      * the stored register received the result of a call within the last three
        instructions, i.e. a value that came from the stream.

    The second flag decays.  The first version of this let "result of a call"
    persist indefinitely, so any register ever written by a bl stayed eligible
    and the field set grew without bound -- the same failure as a running
    register-state filter that cannot be falsified.  A call result is good for
    three instructions and no longer.
    """
    reg = {'r0': 0}
    zero = {}
    fresh = {}                   # reg -> instruction index of the producing call
    out = {}
    for i, x in enumerate(ins):
        full = x.mnemonic + ' ' + x.op_str
        m = re.match(r'^mov\s+(r\d+),\s*(r\d+)$', full)
        if m:
            d, s = m.group(1), m.group(2)
            if s in reg:
                reg[d] = reg[s]
            else:
                reg.pop(d, None)
            zero[d] = zero.get(s, False)
            if s in fresh:
                fresh[d] = fresh[s]
            else:
                fresh.pop(d, None)
            continue
        m = re.match(r'^add\s+(r\d+),\s*(r\d+),\s*#(0x[0-9a-f]+|\d+)$', full)
        if m and m.group(2) in reg:
            reg[m.group(1)] = reg[m.group(2)] + int(m.group(3), 0)
            continue
        m = re.match(r'^movs?\s+(r\d+),\s*#(?:0x0+|0)$', full)
        if m:
            zero[m.group(1)] = True
            continue
        m = re.match(r'^str(b)?\s+(r\d+),\s*\[(r\d+)(?:,\s*#(0x[0-9a-f]+|\d+))?'
                     r'\](?:\s*,\s*#(0x[0-9a-f]+|\d+))?$', full)
        if m:
            isb, srcreg, base, disp, post = m.groups()
            ok = zero.get(srcreg, False)
            if not ok and srcreg in fresh and i - fresh[srcreg] <= 3:
                ok = True
            if ok and base in reg:
                off = reg[base] + (int(disp, 0) if disp else 0)
                if post:
                    reg[base] = off + int(post, 0)
                if off > HDR:
                    out[off] = 1 if isb else 4
            continue
        if re.match(r'^blx?\b', full):
            fresh['r0'] = i
            zero['r0'] = False
            continue
        m2 = re.match(r'^\S+\s+(r\d+)(?:\s*,\s*(.*))?$', full)
        if m2:
            r = m2.group(1)
            if len(m2.groups()) > 1 and m2.group(2) is None:
                zero.pop(r, None)
                fresh.pop(r, None)
            else:
                zero[r] = False
                fresh.pop(r, None)
    return out


def main():
    b = SO.read_bytes()
    funcs = find_functions(b, TEXT_OFF, TEXT_END)
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    md.skipdata = False
    syms = dynsym(b)
    saddr = sorted(syms)

    def near(a):
        j = bisect.bisect_right(saddr, a) - 1
        return demangle(syms[saddr[j]]) if j >= 0 else '(unexported)'

    decoded = {}
    tot = bogus = 0
    for s, e in funcs:
        ins = list(md.disasm(b[s:e], s))
        decoded[s] = ins
        tot += len(ins)
        for x in ins:
            if re.match(r'^ldrb?[a-z]{2}$', x.mnemonic) and \
                    x.mnemonic not in ('ldrd', 'ldrex', 'ldrexh'):
                bogus += 1
    print('=== C1  alignment ===')
    print('  functions %d, instructions %d, impossible ldr<cond> %d (%.3f%%)'
          % (len(funcs), tot, bogus, 100.0 * bogus / max(1, tot)))
    ok_align = bogus / max(1, tot) < 0.01
    print('  aligned: %s' % ok_align)
    print()

    # ---- one pass: shape, arity and classification per function ----------
    shapes = {}                  # addr -> (fields, arity, calls_base_ctor)
    for s, ins in decoded.items():
        f = payload_fields(ins)
        w = sorted(o for o, wd in f.items() if wd == 4)
        nb = sorted(o for o, wd in f.items() if wd == 1)
        isctor = any(x.mnemonic == 'blx' and x.op_str == '#0x%x' % BASE_CTOR
                     for x in ins)
        if not w:
            # a single byte field is still a one-field property: that is the
            # boolean, and leaving it out made the detector miss a known class
            if len(nb) == 1:
                shapes[s] = (nb, 1, isctor)
            continue
        lo, hi = w[0], w[-1]
        if (hi - lo) % 4 or set(w) != set(range(lo, hi + 1, 4)):
            continue
        shapes[s] = (w, (hi - lo) // 4 + 1, isctor)

    print('=== C2  calibration: known classes must be detected, with the right')
    print('        arity, and classified as constructors ===')
    print()
    ok = True
    for a, why in sorted(KNOWN_CTORS.items()):
        want = 1 if 'arity 1' in why else 2
        got = shapes.get(a)
        det, ar, cl = (got is not None, got[1] if got else None,
                       got[2] if got else None)
        good = det and ar == want and cl
        ok &= good
        print('  0x%08x %-26s detected %-5s arity %-4s want %-2d ctor %-5s %s'
              % (a, why, det, ar, want, cl, 'OK' if good else 'MISMATCH'))
    print()
    print('  the four-field target 0x%08x: %s'
          % (TARGET_CTOR,
             ('detected, arity %d, ctor %s'
              % (shapes[TARGET_CTOR][1], shapes[TARGET_CTOR][2]))
             if TARGET_CTOR in shapes else 'NOT DETECTED'))
    print()
    print('  calibration: %s' % ('PASSED' if ok else 'FAILED'))
    if not ok:
        print('  no candidates printed -- a detector that misreads known classes')
        print('  has no standing to propose new ones.')
        return
    print()

    by_arity = defaultdict(list)
    for s, (w, n, c) in shapes.items():
        by_arity[n].append((s, w, c, len(decoded[s])))
    print('=== payload shapes found ===')
    for n in sorted(by_arity):
        v = by_arity[n]
        print('  arity %-3d %6d functions   %6d call the base ctor'
              % (n, len(v), sum(1 for _s, _w, c, _l in v if c)))
    print('  total %d' % len(shapes))
    print()

    four = by_arity.get(4, [])
    readers = [(s, w, l) for s, w, c, l in four if not c]
    print('=== the four-field shape ===')
    print('  functions with it      : %d' % len(four))
    print('  of those, constructors : %d' % sum(1 for _s, _w, c, _l in four if c))
    print('  of those, not calling  : %d   <- candidate readers' % len(readers))
    print()

    print('=== candidate readers, ranked by call count ===')
    print()
    ranked = []
    for s, w, l in readers:
        calls = sum(1 for x in decoded[s] if x.mnemonic in ('bl', 'blx'))
        ranked.append((calls, s, w, l))
    ranked.sort(reverse=True)
    print('  calls  addr        fields          len  nearest symbol')
    for c, s, w, n in ranked[:24]:
        print('  %5d  0x%08x  %-14s %4d  %s'
              % (c, s, ','.join(hex(o) for o in w), n, near(s)[:46]))
    print()

    for c, s, w, n in ranked[:2]:
        print('=' * 78)
        print('CANDIDATE READER 0x%08x  (%d calls, fields %s, in %s)'
              % (s, c, ','.join(hex(o) for o in w), near(s)[:40]))
        print('=' * 78)
        for x in decoded[s][:70]:
            mm = re.search(r'\[r\d+,\s*#(0x[0-9a-f]+)\]', x.op_str)
            off = int(mm.group(1), 0) if mm else None
            mk = ''
            if x.mnemonic.startswith('str') and off is not None and off in w:
                mk = '   <<< field %d' % w.index(off)
            print('  %08x  %-8s %-26s%s' % (x.address, x.mnemonic, x.op_str, mk))
        print()

    # ---- and the target constructor, for the record ------------------------
    print('=' * 78)
    print('the arity-4 CONSTRUCTOR 0x%08x, in %s' % (TARGET_CTOR, near(TARGET_CTOR)[:52]))
    print('=' * 78)
    for x in decoded[TARGET_CTOR][:24]:
        print('  %08x  %-8s %-26s' % (x.address, x.mnemonic, x.op_str))
    print()
    print('  its vtable is installed by  ldr r3,[r5,r3] ; adds r3,#8 ; str r3,[r4]')
    print('  so r5+r3 points at the vtable.  Computing it gives the class, and the')
    print('  vtable slot that differs from the other three classes is its reader.')


if __name__ == '__main__':
    main()
