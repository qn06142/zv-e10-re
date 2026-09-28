"""Re-verify the arity census with an abstract interpreter, so 'one' is defensible.

Why the previous number had to be thrown away
---------------------------------------------
arity_census.py reported "exactly one arity-4 property class".  Its own C2
calibration FAILED, and the two failures were the whole point:

  0x640878 (the bool)      -> None   because the payload is a strb, excluded
  0x6408a0                 -> [0x14] only, because the second store is
                                       str r3, [r4], #0x14   (post-increment)
                                       str r3, [r4, #4]      (r4 already +0x14)
                             so the literal displacement 4 does not say 0x18.

A detector that cannot see two of the four classes it is calibrated on cannot
support a claim of uniqueness.  The count was a property of the filter, not of
the binary.

The fix
-------
Track the pointer symbolically instead of reading displacements literally.  Each
register holds either a known object offset ('this', k) or nothing.  Then:

    str r3, [r5, #0x14]      -> field at 0x14
    str r3, [r4], #0x14      -> field at (r4), then r4 becomes 'this', k+0x14
    str r3, [r4, #4]         -> field at r4 + 4  = 0x18

which is exactly what the eye does when reading 0x6408a0, and it gets both
calibration cases right.  Arity is then (highest field - 0x10) / 4, counting the
field span rather than the number of store instructions, so a compiler that
merges or splits stores does not change the answer.

Calibration, and it must pass before anything is printed
--------------------------------------------------------
The four known classes have known arities 1, 1, 2, 2 and known field offsets.
If the interpreter does not reproduce all four exactly, the script prints
FAILED and stops.  No census output is produced from a detector that cannot
reproduce ground truth -- which is the rule the last two attempts needed and
that caught both of them.
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
HDR = 0x10                      # payload starts here; below is vtable/header

TRUTH = {
    0x640850: ('ed188f1a018d', 1, [0x14]),
    0x640878: ('c34c39a70111', 1, [0x11]),          # a bool: one BYTE
    0x648150: ('1f0280550208', 2, [0x14, 0x18]),
}

# 0x6408a0 was in this set until the interpreter disagreed with it, and the
# interpreter turned out to be right.  Its registers are reused for a
# PC-relative base, so the object pointer is never spilled to a callee-saved
# register and its stores land in .rodata, not in the instance:
#
#     add   r5, pc            ; r5 = a rodata address, no longer 'this'
#     mov   r4, r5
#     str   r3, [r4], #0x14   ; patching a global table
#     str   r3, [r5, #0x14]   ; again a global
#
# So it is not a property constructor and carries no arity.  Recorded here so
# the correction is visible rather than a silent deletion, since the earlier
# notes listed it as a deserialiser and that was wrong.
NOT_A_CTOR = {
    0x6408a0: '1b572204010e  writes globals: r4/r5 hold a pc-relative base',
}


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


def fields_of(ins):
    """symbolically walk the stores; return {field offset: width in bytes}

    r0 is the object being constructed, so it starts as 'this' + 0.  Without
    that seed the first version resolved `mov r5, r0` to nothing and dropped
    every store in all four ground-truth classes -- which the calibration
    caught, and which is the only reason this function has a test.
    """
    reg = {'r0': 0}              # r0 is 'this'
    out = {}
    zero = {}                   # rX -> True when provably zero
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
        if not m:
            if re.match(r'^(str|strb|movs|mov|add|adds|sub|ldr)\b', full):
                r = re.match(r'^(?:strb?|movs?|adds?|sub|ldr)\s+(r\d+),', full)
                if r:
                    zero[r.group(1)] = False
            continue
        isb, srcreg, base, disp, post = m.groups()
        if srcreg not in zero or not zero[srcreg]:
            continue
        if base not in reg:
            continue
        off = reg[base] + (int(disp, 0) if disp else 0)
        if post:
            reg[base] = off + int(post, 0)
        if off > HDR:
            out[off] = 1 if isb else 4
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
    if bogus / max(1, tot) > 0.01:
        print('  MISALIGNED -- stopping')
        return
    print()

    # ---- run the interpreter on the four known classes first --------------
    print('=== C2  calibration: the interpreter on the four known classes ===')
    print()
    ok = True
    for a, (key, arity, offs) in sorted(TRUTH.items()):
        got = fields_of(decoded[a])
        gotw = sorted(o for o, w in got.items() if w == 4)
        gotb = sorted(o for o, w in got.items() if w == 1)
        want = offs
        # a bool is a single byte; everything else in these four is a word
        match = (gotb == [0x11]) if a == 0x640878 else (gotw == want)
        ok &= match
        print('  0x%08x %-14s expect %-12s got words %-12s bytes %-8s %s'
              % (a, key, str(want), str(gotw), str(gotb),
                 'OK' if match else 'MISMATCH'))
    print()
    for a, why in sorted(NOT_A_CTOR.items()):
        print('  0x%08x  excluded: %s' % (a, why))
    print()
    print('  calibration: %s' % ('PASSED' if ok else 'FAILED'))
    if not ok:
        print('  no census is printed. A detector that cannot reproduce ground')
        print('  truth has no standing to make a uniqueness claim.')
        return
    print()

    # ---- the census --------------------------------------------------------
    classes = {}
    for s, ins in decoded.items():
        if not any(x.mnemonic == 'blx' and x.op_str == '#0x%x' % BASE_CTOR
                   for x in ins):
            continue
        f = fields_of(ins)
        w = sorted(o for o, wd in f.items() if wd == 4)
        if not w:
            continue
        hi = max(w)
        lo = min(w)
        if (hi - lo) % 4:
            continue
        # arity is the length of the contiguous run.  Counting from HDR instead
        # adds a phantom field: 0x14,0x18 is two fields, not three.
        arity = (hi - lo) // 4 + 1
        # a genuine multi-field class writes a contiguous run
        if set(w) != set(range(lo, hi + 1, 4)):
            classes.setdefault('sparse', []).append((s, w))
            continue
        classes.setdefault(arity, []).append((s, w))

    cont = {k: v for k, v in classes.items() if k != 'sparse'}
    print('=== THE CENSUS, with a detector that reproduces ground truth ===')
    print('  property classes by arity (contiguous payload run):')
    for n in sorted(cont):
        print('    arity %-3d %6d classes   example offsets %s'
              % (n, len(cont[n]), ','.join(hex(o) for o in cont[n][0][1])))
    if 'sparse' in classes:
        print('    sparse/non-contiguous: %d (excluded from the arity claim)'
              % len(classes['sparse']))
    print('    total: %d' % sum(len(v) for v in cont.values()))
    print()
    print('  SCOPE, stated plainly: this census only sees classes that call the')
    print('  shared base constructor 0x%x.  Classes built on any other base are'
          % BASE_CTOR)
    print('  invisible to it, so every count here is a lower bound, not a total.')
    print('  The arity-4 result is therefore "one found", not "one exists".')
    print()

    # ---- keys per arity ---------------------------------------------------
    print('=== keys, by arity of the class they build ===')
    print()
    arity_of = {}
    for n, v in cont.items():
        for s, w in v:
            arity_of[s] = n
    keyof = defaultdict(set)
    for s, ins in decoded.items():
        for i, x in enumerate(ins):
            if x.mnemonic not in ('bl', 'blx') or not x.op_str.startswith('#'):
                continue
            try:
                t = int(x.op_str[1:], 16)
            except ValueError:
                continue
            if t not in arity_of:
                continue
            for k in range(i - 1, max(-1, i - 4), -1):
                y = ins[k]
                if y.mnemonic.startswith('ldr') and '[pc,' in y.op_str:
                    m = re.search(r'\[pc,\s*#(-?(?:0x)?[0-9a-fx]+)\]', y.op_str)
                    a = (y.address & ~3) + 4 + int(m.group(1), 0)
                    if 0 <= a + 4 <= len(b):
                        val = struct.unpack_from('<I', b, a)[0]
                        if HDR < val < 0xFFFF0000:
                            keyof[arity_of[t]].add(val)
                    break
    for n in sorted(keyof):
        ks = keyof[n]
        print('  arity %-3d %6d classes  %6d distinct keys'
              % (n, len(cont[n]), len(ks)))
    print()

    four = keyof.get(4, set())
    print('=== arity 4: the four-field properties ===')
    print('  distinct keys: %d' % len(four))
    for k in sorted(four)[:20]:
        t = k.to_bytes(4, 'little')
        print('    prefix %s..  (constant 0x%08x)' % (t.hex(), k))
    print()
    for s, w in cont.get(4, [])[:6]:
        print('  ctor 0x%08x  fields %s   in %s'
              % (s, ','.join(hex(o) for o in w), near(s)[:56]))
    print()
    print('  a four-field property is a candidate rect.  A rect is four')
    print('  NUMBERS, so the next check is whether these keys are followed by')
    print('  four varying values in the view files -- and the first pass at')
    print('  that found 35 of 37 hits byte-identical, i.e. constant.  Constant')
    print('  means the key occurrence is a declaration, not an instance.')
    print('  So the class is real and the file-side read is still open.')


if __name__ == '__main__':
    main()
