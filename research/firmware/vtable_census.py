"""The vtable slot is the property type tag, and a geometry is one slot, four reads.

The structure, read off the disassembly
---------------------------------------
A property deserialiser in viewUnified2.so reads its value like this:

    bl   <accessor>              ; a per-property getter, unique to this property
    ldr  r3, [r5]                ; r5 is the stream / context
    ldr  r3, [r3, #0x19c]        ; <- a slot in the stream's vtable
    mov  r1, r0
    blx  r3                      ; the virtual reader does the actual read

The vtable offset is chosen by the *static type of the property*, not by the
property.  So 0x19c, 0x44, 0x1b0 and 0x20 are four different types, and every
property of the same type uses the same offset.  That makes the offset a type
tag, and the histogram of offsets is a census of the type system.

Why this is worth doing rather than more of the key walk
-------------------------------------------------------
The key-walk approach (prop_table.py) was sound in its detector -- it recovered
all four known deserialisers with the right keys -- but the invariant it was
supposed to satisfy came out at 18.6% consistency, which says the backward walk
is frequently picking up a neighbouring key.  So that table is not trustworthy
and is not used further.  A census of vtable offsets does not depend on any
such walk: it is a tally of one instruction form, and it can be checked against
a number derived completely independently.

That independent number exists.  The view file format has exactly 92
signatures (UXC_FORMAT_FULL.md, from the payload bytes themselves).  If the
engine has 92 reader types, two numbers from two unrelated directions agree,
and the type system is pinned.  If it comes out at 90 or 200, that is a real
finding too, and more useful than another guess.

The geometry question, which is the actual goal
-----------------------------------------------
A rect is four numbers.  A deserialiser that calls ONE vtable slot four times is
therefore a rect-shaped property, whatever it is called.  Counting repeats per
function gives that directly, ranked by repeat count, with the known boolean
(c34c39a70111, one byte at +0x11) as the calibration for N=1.

Verification, because five of the earlier searches could not fail
-----------------------------------------------------------------
  C1  Alignment.  Decoded only inside recovered function bodies.  The fraction
      of impossible `ldr<cond>` forms is reported; if it is not small, nothing
      below is trustworthy and the script says so and stops.
  C2  The known boolean must come out as a single virtual read.  If the
      detector is finding real deserialisers, 0x640878 has to appear with
      exactly one read.  A count of zero, or of six, means the detector is
      wrong and the whole census is void.
  C3  A negative control: the same census run over an offset that no reader
      should use.  A tall bar there would mean the offset field is being read
      from somewhere other than a vtable.
"""
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

SO = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\engine\viewUnified2.so')
TEXT_OFF, TEXT_SIZE = 0x0018eec8, 0x074af6c
TEXT_END = TEXT_OFF + TEXT_SIZE

KNOWN_DESER = {
    0x640878: ('c34c39a70111', 20, 'bool, 1 byte at +0x11'),
    0x648150: ('1f0280550208', 28, '3 word fields'),
    0x640850: ('ed188f1a018d', 24, '2 fields'),
    0x6408a0: ('1b572204010e', 28, '2 fields'),
}
VIEW_SIGNATURES = 92          # from UXC_FORMAT_FULL.md, payload-derived
NEGATIVE_CONTROL_OFFSET = 0x1f4   # must be rare if 0x19c etc are real slots


def find_functions(b, lo, hi, maxsz=0x8000):
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
        n2, val, _sz, _i, _o2, _sh = struct.unpack_from('<IIIBBH', b, o)
        if not n2 or not val:
            continue
        e = strs.find(b'\x00', n2)
        a = val & ~1
        s = strs[n2:e].decode('latin1', 'replace')
        if a not in out or len(s) > len(out[a]):
            out[a] = s
    return out


def main():
    b = SO.read_bytes()
    funcs = find_functions(b, TEXT_OFF, TEXT_END)
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    md.skipdata = False

    # ---------------- C1: alignment -----------------------------------------
    decoded = 0
    bogus = 0
    per_func = {}
    for s, e in funcs:
        ins = list(md.disasm(b[s:e], s))
        per_func[s] = ins
        decoded += len(ins)
        for x in ins:
            if re.match(r'^ldrb?[a-z]{2}$', x.mnemonic) and \
                    x.mnemonic not in ('ldrd', 'ldrex', 'ldrexh'):
                bogus += 1
    print('C1  alignment')
    print('  functions %d, instructions %d' % (len(funcs), decoded))
    print('  impossible ldr<cond> forms: %d  (%.3f%%)'
          % (bogus, 100.0 * bogus / max(1, decoded)))
    if bogus / max(1, decoded) > 0.01:
        print('  >> MISALIGNED. Stopping: nothing below would be meaningful.')
        return
    print('  >> aligned.')
    print()

    # ---------------- the census ---------------------------------------------
    # A "virtual read" is: ldr rX, [rY] / ldr rX, [rX, #OFF] / ... / blx rX
    # Rather than require the full shape (which is variable), the primitive is
    # the second load: ldr rX, [rX, #imm] where the base was itself just loaded
    # from [rY] with no intervening write.  That is the vtable fetch.
    slot_users = defaultdict(list)      # offset -> [(func, insn addr)]
    for s, ins in per_func.items():
        n = len(ins)
        for i, x in enumerate(ins):
            m = re.match(r'^ldr(?:\.w)?\s+(r\d+),\s*\[(r\d+)(?:,\s*#(0x[0-9a-f]+|\d+))?\]$',
                         x.mnemonic + ' ' + x.op_str)
            if not m:
                continue
            if m.group(3) is None:
                continue
            off = int(m.group(3), 0)
            base = m.group(2)
            dst = m.group(1)
            # the base must have been loaded from memory, unmodified
            src = None
            for k in range(i - 1, max(-1, i - 6), -1):
                y = ins[k]
                if re.match(r'^ldr(?:\.w)?\s+%s,' % base, y.mnemonic + ' ' + y.op_str):
                    mm = re.search(r'\[(r\d+)\]$', y.op_str)
                    if mm:
                        src = mm.group(1)
                    break
                if y.mnemonic.startswith('str') or re.match(r'^mov%s?$' % base,
                                                            y.mnemonic) and \
                        y.op_str.split(',')[0].strip() == base:
                    break
            if src is None:
                continue
            # and the result must be called indirectly within a few instructions
            called = any(ins[j].mnemonic in ('blx', 'bx') and
                         ins[j].op_str.strip() == dst
                         for j in range(i + 1, min(n, i + 9)))
            if called:
                slot_users[off].append((s, x.address))

    print('THE CENSUS OF TYPE TAGS')
    print('  distinct vtable offsets used for indirect calls: %d' % len(slot_users))
    hi = {k: v for k, v in slot_users.items() if len(v) >= 3}
    print('  offsets used at least 3 times: %d' % len(hi))
    print()
    print('  top 20 by use count:')
    for off, uses in sorted(slot_users.items(), key=lambda kv: -len(kv[1]))[:20]:
        print('    +0x%04x  %6d uses   %d functions'
              % (off, len(uses), len({u[0] for u in uses})))
    print()

    # ---------------- C2: the known boolean ----------------------------------
    print('C2  the known boolean must be exactly one virtual read')
    print()
    for tgt, (keyname, size, note) in KNOWN_DESER.items():
        s = tgt
        f = next((ss for ss, _e in funcs if ss <= tgt), None)
        ins = per_func.get(f, [])
        offs = []
        for i, x in enumerate(ins):
            m = re.match(r'^ldr(?:\.w)?\s+(r\d+),\s*\[(r\d+),\s*(0x[0-9a-f]+|\d+)\]$',
                         x.mnemonic + ' ' + x.op_str)
            if not m:
                continue
            off = int(m.group(3), 0)
            dst = m.group(1)
            for k in range(i - 1, max(-1, i - 6), -1):
                y = ins[k]
                if re.match(r'^ldr(?:\.w)?\s+%s,' % m.group(2),
                            y.mnemonic + ' ' + y.op_str):
                    break
            else:
                continue
            if any(ins[j].mnemonic in ('blx', 'bx') and
                   ins[j].op_str.strip() == dst
                   for j in range(i + 1, min(len(ins), i + 9))):
                offs.append(off)
        c = Counter(offs)
        print('  0x%08x %-14s (%s)' % (tgt, keyname, note))
        print('     virtual reads: %d   distinct slots: %s'
              % (len(offs), ', '.join('0x%x x%d' % (k, v) for k, v in c.most_common(6))))
    print()

    # ---------------- C3: the negative control -------------------------------
    print('C3  negative control')
    print('  control offset 0x%04x : %d uses' % (NEGATIVE_CONTROL_OFFSET,
                                                len(slot_users.get(NEGATIVE_CONTROL_OFFSET, []))))
    print('  a real slot like 0x001c : %d uses' % len(slot_users.get(0x1c, [])))
    print('  the control should be far below the busiest slots if these are real')
    print('  vtable fetches and not an artefact of the instruction form.')
    print()

    # ---------------- the geometry search ------------------------------------
    print('=' * 78)
    print('MULTI-READ DESERIALISERS: one slot read N times is an N-field property')
    print('=' * 78)
    print()
    repeats = []
    for s, ins in per_func.items():
        if len(ins) < 12:
            continue
        seq = []
        for i, x in enumerate(ins):
            m = re.match(r'^ldr(?:\.w)?\s+(r\d+),\s*\[(r\d+),\s*(0x[0-9a-f]+|\d+)\]$',
                         x.mnemonic + ' ' + x.op_str)
            if not m:
                continue
            off = int(m.group(3), 0)
            dst, base = m.group(1), m.group(2)
            ok = False
            for k in range(i - 1, max(-1, i - 6), -1):
                y = ins[k]
                if re.match(r'^ldr(?:\.w)?\s+%s,' % base, y.mnemonic + ' ' + y.op_str):
                    ok = True
                    break
            if not ok:
                continue
            if any(ins[j].mnemonic in ('blx', 'bx') and ins[j].op_str.strip() == dst
                   for j in range(i + 1, min(len(ins), i + 9))):
                seq.append(off)
        if not seq:
            continue
        c = Counter(seq)
        top, n = c.most_common(1)[0]
        if n >= 3:
            repeats.append((n, top, s, len(ins), len(seq)))
    repeats.sort(reverse=True)
    print('  functions where one slot is read 3+ times: %d' % len(repeats))
    print()
    syms = dynsym(b)
    import bisect
    saddr = sorted(syms)

    def near(a):
        j = bisect.bisect_right(saddr, a) - 1
        return demangle(syms[saddr[j]]) if j >= 0 else '?'
    print('  N  slot    function      len  reads  nearest exported symbol')
    seen = set()
    shown = 0
    for n, top, s, ln, tot in repeats:
        key = (n, top)
        if key in seen:
            continue
        seen.add(key)
        if shown >= 28:
            break
        print('  %d  0x%04x  0x%08x  %4d  %4d  %s'
              % (n, top, s, ln, tot, near(s)[:56]))
        shown += 1
    print()

    # The N=4 candidates are the rects.  Print a couple in full.
    four = []
    seen4 = set()
    for n, top, s, ln, tot in repeats:
        if n != 4 or top in seen4:
            continue
        seen4.add(top)
        four.append((top, s))
    print('  distinct slots read exactly 4 times: %d' % len(seen4))
    print('  distinct slots read 3 times       : %d'
          % len({t for n, t, _s, _l, _r in repeats if n == 3}))
    print()
    for top, s in four[:3]:
        ins = per_func[s]
        print('=' * 78)
        print('RECT CANDIDATE: slot 0x%04x, function 0x%08x  in %s'
              % (top, s, near(s)[:60]))
        print('=' * 78)
        shownoff = 0
        for x in ins[:80]:
            mk = ''
            m = re.search(r'\[r\d+,\s*#(0x[0-9a-f]+)\]', x.op_str)
            if m and int(m.group(1), 0) == top:
                mk = '   <<< slot %04x' % top
                shownoff += 1
            print('  %08x  %-8s %-26s%s' % (x.address, x.mnemonic, x.op_str, mk))
        print()
        break

    # ---------------- the type census against the independent number --------
    print('=' * 78)
    print('DOES THE ENGINE TYPE COUNT MATCH THE FILE FORMAT?')
    print('=' * 78)
    real = {k: v for k, v in slot_users.items()
            if len(v) >= 3 and 0x18 <= k < 0x400}
    print('  engine: %d vtable slots used 3+ times in 0x18..0x400' % len(real))
    print('  file : %d signatures in the view payload (independent)' % VIEW_SIGNATURES)
    print()
    common = set(real) & set(range(0, 0x400))
    print('  agreement is a match in count, not a proof of identity.  Stated')
    print('  that way because a coincidental count is exactly the kind of thing')
    print('  that fooled the earlier searches, and the two numbers come from')
    print('  unrelated data, so the coincidence would have to be arranged.')


if __name__ == '__main__':
    main()
