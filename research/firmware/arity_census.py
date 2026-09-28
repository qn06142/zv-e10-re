"""Property arity = the number of payload fields the constructor zeroes.

What the four ground-truth classes actually are
-----------------------------------------------
The previous analysis called 0x640850 / 0x640878 / 0x6408a0 / 0x648150
"deserialisers".  Reading them in full refutes that.  All four are the same
twenty-eight byte function:

    push {r4, r5, r7, lr}
    ldr  rX, [pc, #N]
    mov  rY, r0
    blx  0x1872c8          ; base-class constructor
    ldr  r3, [pc, #N]
    add  r4, pc
    mov  r0, r5
    ldr  r3, [r4, r3]      ; the class vtable
    adds r3, #8
    str  r3, [r5]          ; install vtable+8 at offset 0
    movs r3, #0
    str  r3, [r5, #0x14]   ; zero the payload
    pop  {r4, r5, r7, pc}

Not one instruction reads the input stream.  They are constructors: build the
base, install the vtable, zero the payload.  So the earlier statement that the
boolean "is stored as a byte at +0x11" was true of the *zeroing*, and the
`strb` was never evidence of a deserialiser.  The `== 1` predicate found
downstream is still solid -- that was code, read directly.

Why this is the geometry
------------------------
A constructor that zeroes four consecutive payload fields is describing a
four-field property.  A rect is four numbers.  So the constructors fall into
arity classes, and the arity-4 class is the geometry -- found by counting, not
by looking for a rect-shaped byte pattern in a payload, which is the search
that produced six false structures.

The calibration is not optional
-------------------------------
The four known classes give ground truth: one zeroes a single byte at +0x11,
one zeroes a single word at +0x14, two zero two words at +0x14 and +0x18.  If
the detector does not reproduce arity 1, 1, 2, 2 for those four addresses, it is
broken and the rest of the census is void.  This is the C2-style control that
the last two attempts needed and that caught both of them.

Detection
---------
The fingerprint is the call to the shared base constructor 0x1872c8 followed by
an install-vtable sequence, then a run of stores of a register known to be zero.
Requiring the *zero* is what separates a constructor from an ordinary function
that happens to call the same helper: `movs r3, #0` immediately before the
stores.  Stores whose offset is 0, 4 or 8 are the vtable/header, not payload, so
payload counting starts above them.

What it buys
------------
Arity 4 constructors, each with the class vtable, give a set of four-field
property classes.  The class vtable address is a handle into the binary, and
from a handle the same method that named the boolean works: find the consumer,
read the enclosing exported symbol, and the property is named.  A named
four-field property is a thing that can be edited in the view files.
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

# ground truth: address -> (key, expected arity, expected offsets)
TRUTH = {
    0x640850: ('ed188f1a018d', 1, [0x14]),
    0x640878: ('c34c39a70111', 1, [0x11]),
    0x6408a0: ('1b572204010e', 2, [0x14, 0x18]),
    0x648150: ('1f0280550208', 2, [0x14, 0x18]),
}
PAYLOAD_FLOOR = 0x10          # offsets at or below this are header/vtable


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


def mem_off(op):
    """displacement in [rX, #imm], or None"""
    m = re.search(r'\[r\d+,\s*#(0x[0-9a-f]+|\d+)\]', op)
    return int(m.group(1), 0) if m else None


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

    print('=== C1  alignment ===')
    total = bogus = 0
    decoded = {}
    for s, e in funcs:
        ins = list(md.disasm(b[s:e], s))
        decoded[s] = ins
        total += len(ins)
        for x in ins:
            if re.match(r'^ldrb?[a-z]{2}$', x.mnemonic) and \
                    x.mnemonic not in ('ldrd', 'ldrex', 'ldrexh'):
                bogus += 1
    print('  functions %d, instructions %d' % (len(funcs), total))
    print('  impossible ldr<cond>: %d (%.3f%%)'
          % (bogus, 100.0 * bogus / max(1, total)))
    aligned = bogus / max(1, total) < 0.01
    print('  aligned: %s' % aligned)
    print()

    # ---------------- detector ---------------------------------------------
    ctor = {}
    for s, ins in decoded.items():
        if not ins:
            continue
        if not any(x.mnemonic == 'blx' and x.op_str == '#0x%x' % BASE_CTOR
                   for x in ins):
            continue
        # For each store of a payload offset, require the register being stored
        # to have been zeroed within the previous four instructions.  Local
        # rather than a running set: a running "this register is zero" flag is
        # wrong the moment the register is reused, and the first version of this
        # had exactly that bug and matched nothing.  Four instructions is the
        # window the ground-truth functions actually use (three).
        payload = []
        for i, x in enumerate(ins):
            if not x.mnemonic.startswith('str'):
                continue
            m = re.match(r'^str\s+(r\d+),', x.mnemonic + ' ' + x.op_str)
            if not m:
                continue
            reg = m.group(1)
            off = mem_off(x.op_str)
            if off is None or off <= PAYLOAD_FLOOR:
                continue
            zeroed = False
            for k in range(i - 1, max(-1, i - 5), -1):
                y = ins[k]
                if re.match(r'^movs?\s+%s,\s*#(?:0x0+|0)$' % reg,
                            y.mnemonic + ' ' + y.op_str):
                    zeroed = True
                    break
            if zeroed:
                payload.append(off)
        if payload:
            ctor[s] = sorted(set(payload))
    print('=== detector: functions calling the base constructor 0x%x ===' % BASE_CTOR)
    print('  with payload fields zeroed: %d' % len(ctor))
    print()

    # ---------------- C2  calibration ---------------------------------------
    print('=== C2  calibration against the four known classes ===')
    print('  (if these do not come out right, the census below is void)')
    print()
    print('  addr       key              expect            got')
    allok = True
    for a, (key, arity, offs) in sorted(TRUTH.items()):
        got = ctor.get(a)
        ok = (got == offs)
        allok &= ok
        print('  0x%08x  %-14s  arity %d %-10s  %-14s %s'
              % (a, key, arity, str(offs), str(got), 'OK' if ok else 'MISMATCH'))
    print()
    print('  calibration: %s' % ('PASSED' if allok else 'FAILED'))
    print()

    # ---------------- the arity census --------------------------------------
    print('=== THE ARITY CENSUS ===')
    hist = Counter(len(v) for v in ctor.values())
    print('  %d property classes by payload-field count' % len(ctor))
    print()
    print('  arity   classes   offsets seen')
    for n in sorted(hist):
        pats = Counter(tuple(v) for v in ctor.values() if len(v) == n)
        top = pats.most_common(3)
        s = '  '.join('%s x%d' % (','.join(hex(o) for o in p), c)
                      for p, c in top)
        print('    %2d   %6d   %s' % (n, hist[n], s[:88]))
    print()

    four = sorted(s for s, v in ctor.items() if len(v) == 4)
    print('=== arity-4 classes: the geometry candidates ===')
    print('  %d classes zero exactly four fields' % len(four))
    print()
    pats = Counter(tuple(ctor[s]) for s in four)
    print('  distinct offset patterns:')
    for p, c in pats.most_common(12):
        print('    %-28s %4d classes' % (','.join(hex(o) for o in p), c))
    print()

    # For each arity-4 class, find which keys reference it.  A key is loaded
    # pc-relative immediately before a call to the class's vtable-taking ctor.
    print('=== keys that build an arity-4 class ===')
    print()
    fourset = set(four)
    keyof = defaultdict(set)
    for s, ins in decoded.items():
        for i, x in enumerate(ins):
            if x.mnemonic not in ('bl', 'blx') or not x.op_str.startswith('#'):
                continue
            try:
                t = int(x.op_str[1:], 16)
            except ValueError:
                continue
            if t not in fourset:
                continue
            for k in range(i - 1, max(-1, i - 4), -1):
                y = ins[k]
                if y.mnemonic.startswith('ldr') and '[pc,' in y.op_str:
                    m = re.search(r'\[pc,\s*#(-?(?:0x)?[0-9a-fx]+)\]', y.op_str)
                    v = int(m.group(1), 0)
                    a = (y.address & ~3) + 4 + v
                    if 0 <= a + 4 <= len(b):
                        val = struct.unpack_from('<I', b, a)[0]
                        if PAYLOAD_FLOOR < val < 0xFFFF0000:
                            keyof[t].add(val)
                    break
    tot = sum(len(v) for v in keyof.values())
    print('  arity-4 classes referenced with a key: %d' % len(keyof))
    print('  distinct keys: %d' % len({k for v in keyof.values() for k in v}))
    print()
    rows = []
    for s, ks in keyof.items():
        rows.append((len(ks), s, ks))
    rows.sort(reverse=True)
    print('  keys   ctor        payload offsets    nearest exported symbol')
    for n, s, ks in rows[:20]:
        kb = []
        for k in sorted(ks)[:3]:
            t = k.to_bytes(4, 'little') + b'\x00'
            kb.append(t[:6].hex())
        print('  %4d   0x%08x  %-18s %s' % (n, s, ','.join(hex(o) for o in ctor[s]),
                                            ','.join(kb)) + '  ' + near(s)[:40])
    print()

    # dump the most-used arity-4 class in full, so the claim can be read
    if rows:
        n, s, ks = rows[0]
        print('=' * 78)
        print('most-used arity-4 class: ctor 0x%08x, %d keys, in %s'
              % (n, s, near(s)[:56]))
        print('  payload offsets: %s' % ', '.join(hex(o) for o in ctor[s]))
        print('=' * 78)
        for x in decoded[s][:44]:
            off = mem_off(x.op_str)
            mk = ''
            if off is not None and off in ctor[s] and x.mnemonic.startswith('str'):
                mk = '   <<< payload field %d' % ctor[s].index(off)
            print('  %08x  %-8s %-26s%s' % (x.address, x.mnemonic, x.op_str, mk))
        print()
        kb = []
        for k in sorted(ks)[:12]:
            t = k.to_bytes(4, 'little') + b'\x00'
            kb.append(t[:6].hex())
        print('  its keys: %s' % ' '.join(kb))


if __name__ == '__main__':
    main()
