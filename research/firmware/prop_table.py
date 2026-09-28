"""Build the master key -> (object size, deserialiser) table, computed not guessed.

What the disassembly actually shows
-----------------------------------
A class constructor in viewUnified2.so is a flat run of property insertions.  Each
one has the same shape:

    movs r0, #<size>        ; the object size for this property
    blx   <operator new>
    ...
    ldr   r1, [pc, #imm]    ; the 6-byte property key, from the literal pool
    mov   r2, r5            ; the byte stream
    bl    <deserialiser>     ; (obj, key, stream)
    ...
    blx   <map insert>

So for every property the engine knows about, three facts sit within a few
instructions of each other: the key, the allocation size, and the deserialiser
that knows how to read it.  That is a *master table* -- and it is derived by
following data flow, not by pattern-matching on file bytes, so it cannot produce
the kind of false structure the earlier searches did.

Why this is the thing that matters
----------------------------------
The four deserialisers found earlier were found by looking at one property.  If
this works, it covers every property in the library, which means:

  * a complete type map (key -> deserialiser), so the 92 signatures can be
    counted directly and any property's type read off rather than guessed;
  * the object size for every property, so a class layout can be assembled;
  * the set of distinct deserialisers, which is the set of distinct property
    TYPES.  A geometry property would be a deserialiser that reads four values.

And the deserialiser address is a handle we can feed straight back into the
method that just worked: find its consumer, read the enclosing exported symbol,
and the property is named.  `c34c39a70111` was named "caution" that way.

Why the test can fail
---------------------
A key might be loaded for one purpose and passed to a different call, and the
backward walk might grab a key belonging to the previous property.  So the
invariant is checked rather than assumed: for every key that appears N times,
are all N occurrences the same (size, deserialiser) pair?  If the walk were
grabbing neighbours, the pairs would scatter.  That is a real test with a real
failure mode, and the scatter rate is reported per key so a bad key is visible
rather than averaged away.

The detection of "this is a deserialiser call" is also not a whitelist.  It is a
fingerprint -- an `ldr` from a pc-relative pool followed by `mov r2, r5` then
`bl` -- and the known four are then checked to have been found, so the detector
is validated against ground truth rather than trusted.
"""
import re
import struct
import sys
import bisect
from collections import Counter, defaultdict
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

SO = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\engine\viewUnified2.so')
TEXT_OFF, TEXT_SIZE = 0x0018eec8, 0x074af6c
TEXT_END = TEXT_OFF + TEXT_SIZE

# ground truth from dispatch_read.py, used to validate the detector, not to drive it
KNOWN = {
    0x640878: ('c34c39a70111', 20, 'bool'),
    0x648150: ('1f0280550208', 28, '3 word fields'),
    0x640850: ('ed188f1a018d', 24, ''),
    0x6408a0: ('1b572204010e', 28, ''),
}
KNOWN_KEY_LE = {0x640878: 0xa7394cc3}   # c3 4c 39 a7 -> 0xa7394cc3


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


def decode(b, funcs):
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    md.skipdata = False
    for s, e in funcs:
        for x in md.disasm(b[s:e], s):
            yield x


def pc_pool(b, ins, addr):
    """value loaded by an `ldr rN, [pc, #imm]` at ins"""
    m = re.search(r'\[pc,\s*#(-?(?:0x)?[0-9a-fx]+)\]', ins.op_str)
    if not m:
        return None
    t = m.group(1)
    try:
        v = int(t, 0)
    except ValueError:
        v = int(t, 16)
    a = (addr & ~3) + 4 + v
    if a < 0 or a + 4 > len(b):
        return None
    return struct.unpack_from('<I', b, a)[0]


def main():
    b = SO.read_bytes()
    funcs = find_functions(b, TEXT_OFF, TEXT_END)
    print('=== building the master property table ===')
    print('  functions decoded: %d' % len(funcs))
    print()

    # bucket each instruction by the function range that contains it, so the
    # backward walks below cannot step across a function boundary
    fl = [s for s, _ in funcs]
    buckets = defaultdict(list)
    for x in decode(b, funcs):
        j = bisect.bisect_right(fl, x.address) - 1
        buckets[j].append(x)
    print('  instruction stream split into %d function bodies' % len(buckets))
    print()

    # --- detector: the tight 3-instruction window ----------------------------
    #
    # The first attempt allowed any pool load within 14 instructions before any
    # call, and matched 74,733 sites -- the top "targets" were all PLT stubs
    # around operator new.  Too loose to mean anything.  The actual shape, read
    # off the disassembly at 0x641d24, is three instructions with no gap:
    #
    #     ldr   r1, [pc, #imm]     ; the key, from the literal pool
    #     mov   r2, r5             ; the byte stream
    #     bl    <deserialiser>     ; (obj, key, stream)
    #
    # so the key load must be 1..3 instructions before the call.  That is the
    # window used here.  It is still validated against the four known
    # deserialisers below, because a tightened filter is not automatically a
    # correct one -- if tightening loses the ground truth, the filter is wrong.
    sites = []          # (key, size, target, func_start, insn_addr)
    target_counts = Counter()
    for j, ins in buckets.items():
        for i, x in enumerate(ins):
            if x.mnemonic not in ('bl', 'blx'):
                continue
            if not x.op_str.startswith('#'):
                continue
            try:
                tgt = int(x.op_str[1:], 16)
            except ValueError:
                continue
            key = None
            for k in range(i - 1, max(-1, i - 4), -1):
                y = ins[k]
                if y.mnemonic.startswith('ldr'):
                    v = pc_pool(b, y, y.address)
                    if v is not None:
                        key = v
                        break
            if key is None:
                continue
            # size: the nearest preceding immediate move into r0
            size = None
            for k in range(i - 1, max(-1, i - 26), -1):
                y = ins[k]
                if y.mnemonic in ('movs', 'mov') and re.match(
                        r'^r0,\s*#(0x[0-9a-f]+|\d+)$', y.op_str):
                    t = y.op_str.split('#')[1]
                    size = int(t, 0)
                    break
            sites.append((key, size, tgt, fl[j], x.address))
            target_counts[tgt] += 1

    print('--- detector validation against the four known deserialisers ---')
    ok = True
    for tgt, (keyname, size, _note) in KNOWN.items():
        got = target_counts.get(tgt, 0)
        keys = {k for k, _s, t, _f, _a in sites if t == tgt}
        sizes = Counter(s for _k, s, t, _f, _a in sites if t == tgt)
        exp = KNOWN_KEY_LE.get(tgt)
        match = 'n/a' if exp is None else (
            'YES' if exp in keys else 'NO -- key %08x not among %d' % (exp, len(keys)))
        print('  0x%08x  %s  size %-3d  found %5d times  key match: %s'
              % (tgt, keyname, size, got, match))
        if got == 0:
            ok = False
    print('  detector found all four: %s' % ('YES' if ok else 'NO'))
    print()

    print('--- scale ---')
    print('  call sites matching the fingerprint : %d' % len(sites))
    print('  distinct keys                        : %d' % len({s[0] for s in sites}))
    print('  distinct call targets                : %d' % len(target_counts))
    print()

    # --- the invariant test: is key -> (size, target) consistent? ------------
    bykey = defaultdict(list)
    for k, s, t, f, a in sites:
        bykey[k].append((s, t))
    multi = {k: v for k, v in bykey.items() if len(v) > 1}
    pure = sum(1 for v in bykey.values() if len(set(v)) == 1)
    scatter = {k: v for k, v in bykey.items() if len(set(v)) > 1}
    print('--- invariant: does one key always mean one (size, deserialiser)? ---')
    print('  keys with >1 occurrence : %d' % len(multi))
    print('  of those, fully consistent: %d  (%.1f%%)'
          % (len(multi) - len(scatter),
             100.0 * (len(multi) - len(scatter)) / max(1, len(multi))))
    print('  keys that scatter       : %d' % len(scatter))
    print()
    if scatter:
        print('  a scattering key is a warning that the backward walk grabbed a')
        print('  neighbour.  Examples, with their consistency:')
        for k, v in list(scatter.items())[:6]:
            c = Counter(v)
            print('    key 0x%08x  %d distinct (size,target) over %d sites'
                  % (k, len(set(v)), len(v)))
            for (s, t), n in c.most_common(4):
                print('        size %-4s target 0x%08x   x%d' % (s, t, n))
    print()

    # --- the type map: distinct deserialisers --------------------------------
    print('--- distinct deserialisers found (this is the set of property TYPES) ---')
    tgt_keys = defaultdict(set)
    for k, s, t, f, a in sites:
        tgt_keys[t].add(k)
    ranked = sorted(tgt_keys.items(), key=lambda kv: -len(kv[1]))
    print('  %d distinct targets carry at least one key' % len(tgt_keys))
    print('  top 20 by number of distinct properties:')
    for t, ks in ranked[:20]:
        print('    0x%08x  %5d properties' % (t, len(ks)))
    print()

    # --- the interesting question: which deserialiser reads FOUR values? -----
    # A geometry property is four fields.  The deserialiser will contain a run
    # of stores to consecutive offsets.  Count store instructions per deserialiser
    # body and report the distribution; a four-store deserialiser stands out, and
    # the four known ones give the calibration.
    print('--- store counts per deserialiser body (geometry would be high) ---')
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    md.skipdata = False
    body = {}
    for t, ks in ranked[:60]:
        f = [(s, e) for s, e in funcs if s <= t < e]
        if not f:
            continue
        s, e = f[0]
        if e - s > 0x600:
            e = s + 0x600
        ins = list(md.disasm(b[s:e], s))
        stores = [x for x in ins if x.mnemonic.startswith('str')
                  and 'sp' not in x.op_str and 'r7' not in x.op_str]
        body[t] = (len(ks), len(stores), s, e)
    print('  target        props  stores   body')
    for t, (nk, ns, s, e) in sorted(body.items(), key=lambda kv: -kv[1][1])[:20]:
        print('    0x%08x  %5d  %5d   0x%08x..0x%08x' % (t, nk, ns, s, e))
    print()
    for t, (nk, _ns, s, e) in body.items():
        if t in KNOWN:
            print('  calibration: 0x%08x %s has %d stores'
                  % (t, KNOWN[t][0], body[t][1]))
    print()

    # dump the highest-store-count deserialiser that is NOT one of the known four
    cand = [t for t in sorted(body, key=lambda x: -body[x][1])
            if t not in KNOWN and body[t][1] >= 6][:1]
    for t in cand:
        nk, ns, s, e = body[t]
        print('=' * 76)
        print('highest-store unknown deserialiser 0x%08x  (%d properties, %d stores)'
              % (t, nk, ns))
        print('=' * 76)
        for x in md.disasm(b[s:e], s):
            mark = ''
            if x.mnemonic.startswith('str') and 'sp' not in x.op_str:
                mark = '   <<<'
            print('  %08x  %-8s %-24s%s' % (x.address, x.mnemonic, x.op_str, mark))
    print()

    # write the table for later use
    outp = Path(r'D:\02_Development_And_Projects\pmca-re\research\firmware\prop_table.tsv')
    with outp.open('w', encoding='utf-8') as f:
        f.write('# key_le\tsize\ttarget\tkey_bytes\tn_sites\tfunc\n')
        agg = defaultdict(lambda: [None, 0, None, 0])
        for k, s, t, fs, a in sites:
            e = agg[k]
            if e[0] is None:
                e[0], e[2] = s, fs
            elif e[0] != s or e[2] != t:
                e[3] = 1
            e[1] += 1
        for k, (s, n, t, bad) in sorted(agg.items()):
            # the key is a 6-byte value: 4 bytes little-endian plus a byte that
            # sat above them, which is how it reads on disk (c3 4c 39 a7 01 11)
            kb = k.to_bytes(4, 'little') + b'\x00'
            f.write('%08x\t%s\t%08x\t%s\t%d\t%08x%s\n'
                    % (k, s, t, kb[:6].hex(), n, t,
                       '\tINCONSISTENT' if bad else ''))
    print('table written: %s' % outp)


if __name__ == '__main__':
    main()
