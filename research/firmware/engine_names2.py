"""Read the property dispatch table in viewUnified2.so.

What S1 established
-------------------
55 of 56 known property keys appear as u32 constants in viewUnified2.so, with
three of them extremely frequent:

    0xa7394cc3  c34c39a70191   922 occurrences   (the boolean, tag 0x0191)
    0x5580021f  1f0280550208   549 occurrences
    0x0422571b  1b572204010e   462 occurrences

That is not a coincidence: 922 references to one property key is a dispatcher
comparing against it, not data.  So there is a property registry in this
library, and it is the thing UXC_FORMAT_FULL.md says we lack.

libSysDef.so by contrast has zero of the keys and only 18 mangled symbols, all
DefRsrc/MWF infrastructure -- it is a resource-manager catalogue, not the object
model.  The 45.7x palette enrichment there is a default colour scheme, which is
consistent, but it does not name properties.  So the search target was right in
kind and wrong in file; viewUnified2.so is where the names would be.

What to extract
---------------
Each dispatch site is a comparison against a key.  On ARM/Thumb that is a
literal pool load followed by a compare and a branch, so a key constant usually
sits near code that also references a readable string -- an assertion, a log
format, or a property name kept for diagnostics.

So: for each of the 56 keys, take its occurrence offsets, and within a window
around each one look for printable strings.  Where a key has a string that
mentions its own concept, that is the name.  Where a key sits in a dense
literal pool with many keys, that is the registry and can be dumped whole.

The window has to be generous, because Thumb literal pools are often 4-8 KB from
the code that references them, and the linker interleaves .text, .rodata and
.data.  A window of ±4 KB catches most; a second pass at ±32 KB catches the rest
at the cost of noise, which is reported rather than filtered away.

A string is only reported as a candidate naming if it is close to the key AND
the association is not shared by dozens of other keys -- otherwise it is just a
library-wide string that happens to be nearby, and saying so is more useful than
a false name.
"""
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path

ENG = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\engine')
SO = ENG / 'viewUnified2.so'

KNOWN = {
    '1b572204010e': 16, '1f0280550208': 15, 'c34c39a70111': 7,
    '8ac3b3620202': 15, 'ed06f4340100': 7, 'ec18a67a0290': 11,
    'e0435a90018d': 8, '2146adbf018d': 8, '49760d41018d': 8,
    'dbcf0a6c018d': 8, '0fcbce250190': 8, 'ed188f1a018d': 8,
    '4a311dea018c': 8, '7fb68c7f0190': 8, '82d530c60190': 8,
    '03193943018c': 8, '547e85a6018c': 8, '2dac7cb2018c': 8,
    '571c3df3018c': 8, '94899f21018d': 8, '0d4d93430190': 8,
    'd7520f8d018d': 8, 'ae338fba018d': 8, '3254afad018c': 8,
    '1f0b9b400190': 8, 'c3bd3492018d': 8, 'a99afb240190': 8,
    '9975ed000190': 8, '27d4bdf90190': 8, 'b62031c60190': 8,
    'a77eda3b0190': 8, '6b7bfc950111': 7, '78e18641018d': 8,
    '210268a50290': 10, '39b64d380190': 8, '87d407b40190': 8,
    '3efca0c00190': 8, 'cc20b27d0190': 8, '94891ba0018d': 8,
    '3925bfa00401': 17, '3dca858a0190': 8, 'd7e986ec0208': 15,
    '174a483d0190': 8, '4dc0baf80190': 8, 'eb099cef0102': 10,
    'eb099cef0101': 8, '1c0034cb0190': 8, '54eb60d70111': 7,
    '3ea961a70111': 7, '3c19f799018d': 32, '38f85c320408': 40,
    'dd387635028d': 22, 'c34c39a70191': 8, 'eb2c0d180190': 8,
    '95753a130101': 8, '11ddc5e2018c': 8, '448671460111': 7,
    'fd2fad3d0111': 7,
}
KEYS = {}
for sig in KNOWN:
    KEYS[struct.unpack('<I', bytes.fromhex(sig[:8]))[0]] = sig

BOOL_KEY = struct.unpack('<I', bytes.fromhex('c34c39a7'))[0]


def strs_in(b, lo, hi, minlen=4):
    out = []
    chunk = b[lo:hi]
    for m in re.finditer(rb'[\x20-\x7e]{%d,}' % minlen, chunk):
        out.append((lo + m.start(), m.group().decode('latin1')))
    return out


def main():
    b = SO.read_bytes()
    print('=== viewUnified2.so, %d bytes ===' % len(b))
    print()

    # 1. where does the boolean key appear?
    pat = struct.pack('<I', BOOL_KEY)
    offs = []
    s = 0
    while True:
        i = b.find(pat, s)
        if i < 0:
            break
        offs.append(i)
        s = i + 1
    print('boolean key 0x%08x (%s): %d occurrences'
          % (BOOL_KEY, KEYS[BOOL_KEY], len(offs)))
    print()
    print('  first 24 offsets: %s' % ' '.join('0x%08x' % o for o in offs[:24]))
    print()

    # 2. are the offsets clustered? a registry is one region
    print('  clustering of the boolean key:')
    buckets = Counter(o >> 16 for o in offs)
    for hi16, n in buckets.most_common(10):
        print('    block 0x{:04x}0000 .. 0x{:04x}ffff  {:4d} occurrences'
              .format(hi16, hi16, n))
    print()

    # uniform-stride check: a generated table has a fixed period
    g0 = Counter(offs[i + 1] - offs[i] for i in range(len(offs) - 1))
    print('  stride histogram of consecutive occurrences:')
    for g, n in g0.most_common(6):
        print('    stride %d : %d' % (g, n))
    print()

    # 3. the dense literal-pool region
    dens = [(hi16, n) for hi16, n in buckets.items() if n >= 3]
    if dens:
        dens.sort(key=lambda x: -x[1])
        lo = dens[0][0] << 16
        hi = (dens[0][0] + 1) << 16
        print('  densest 64 KB block: 0x%08x..0x%08x (%d boolean refs)'
              % (lo, hi, dens[0][1]))
        other = {}
        for k, sig in KEYS.items():
            n = b.count(struct.pack('<I', k), lo, hi)
            if n:
                other[sig] = n
        print('  %d distinct known keys in that block' % len(other))
        print('  %s' % ', '.join('%s x%d' % (k, v)
                                for k, v in sorted(other.items(), key=lambda kv: -kv[1])[:20]))
        print()

        # 4. dump the key-bearing words in that block, to see the table shape
        print('  --- the registry as u32 words (keys marked K) ---')
        run = []
        for o in range(lo, min(hi, len(b)) - 3, 4):
            v = struct.unpack_from('<I', b, o)[0]
            if v in KEYS:
                run.append((o, v))
        # group into runs with gaps < 64
        groups = []
        cur = [run[0]] if run else []
        for r in run[1:]:
            if r[0] - cur[-1][0] <= 64:
                cur.append(r)
            else:
                groups.append(cur)
                cur = [r]
        if cur:
            groups.append(cur)
        groups.sort(key=lambda g: -len(g))
        for g in groups[:6]:
            print('    run at 0x%08x, %d keys, span 0x%08x..0x%08x'
                  % (g[0][0], len(g), g[0][0], g[-1][0]))
            for o, v in g[:14]:
                # what is the neighbouring word? a handler pointer?
                nb = struct.unpack_from('<I', b, o + 4)[0] if o + 8 <= len(b) else 0
                print('      0x%08x  K %-14s  next 0x%08x%s'
                      % (o, KEYS[v], nb,
                         '  (in-binary)' if lo <= nb < hi else ''))
            if len(g) > 14:
                print('      ... %d more' % (len(g) - 14))
        print()

    # 5. strings near the boolean key, and how exclusive they are
    print('=' * 76)
    print('strings near the boolean key, and whether the association is real')
    print('=' * 76)
    WIN = 4096
    near_for_bool = set()
    for o in offs:
        for so, t in strs_in(b, max(0, o - WIN), min(len(b), o + WIN), 5):
            near_for_bool.add((so, t))
    # how many other keys share each of those strings?
    shared = Counter()
    for k in KEYS:
        if k == BOOL_KEY:
            continue
        kp = struct.pack('<I', k)
        ko = []
        s = 0
        while True:
            i = b.find(kp, s)
            if i < 0:
                break
            ko.append(i)
            s = i + 1
        for o in ko[:40]:
            for so, t in strs_in(b, max(0, o - WIN), min(len(b), o + WIN), 5):
                shared[(so, t)] += 1
    print()
    print('  %d distinct strings within 4 KB of a boolean-key reference'
          % len(near_for_bool))
    excl = [(so, t, shared[(so, t)]) for so, t in near_for_bool
            if shared[(so, t)] == 0]
    print('  %d of them are NOT near any other known key' % len(excl))
    print()
    print('  --- exclusive strings (candidate namings) ---')
    for so, t, _n in sorted(excl)[:60]:
        print('    @0x%08x  %s' % (so, t[:90]))
    if len(excl) > 50:
        print('    ... and %d more' % (len(excl) - 50))
    print()
    print('  --- strings shared with many keys (library noise) ---')
    for (so, t), n in sorted(((k, v) for k, v in shared.items()), key=lambda kv: -kv[1])[:12]:
        print('    @0x%08x  %-70s  near %d keys' % (so, t[:70], n))


if __name__ == '__main__':
    main()
