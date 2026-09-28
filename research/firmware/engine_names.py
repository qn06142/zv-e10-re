"""Search libSysDef.so and viewUnified2.so for the property names.

The plan
--------
Correlation narrowed c34c39a70111 to "a per-widget-type state flag on top-level
objects" and no further, and hash reversal was ruled out: 100,160 candidate
strings across 8 families produced zero hits against 0.001 expected.  So the
names are not a function of anything we can guess.  They exist only in the code
that consumes them.

Two libraries matter, and for different reasons:

  libSysDef.so      45.7x enriched in palette ids -- system defaults, so a
                    property-name table is likely to sit here
  viewUnified2.so   14.3 MB, contains the literal "global.xdb", so it is the
                    loader and the class that owns the object model

What to look for, in order of how much it would settle the question:

  1. The signature bytes as a table.  If the loader dispatches on (key, tag)
     with a switch or a lookup table, the 43 keys we know appear as constants.
     A table of consecutive keys with associated handler pointers is the object
     model's property registry, and the pointers lead to code that names them.

  2. RTTI.  A C++ library compiled with RTTI carries typeinfo records with
     mangled names like _ZN9Jiritsu6Widget... Those demangle to class and method
     names, which is exactly the layer UXC_FORMAT_FULL.md says we are missing.

  3. Readable strings in the vicinity of those regions.  Debug builds and some
     embedded toolchains keep assertion strings; those name properties directly.

  4. The palette-adjacent table.  0x4000..0x4022 appearing 823 times in
     libSysDef.so suggests a default colour scheme, and a default scheme
     usually sits next to a default *style* table with named members.

What this does not do
---------------------
It does not guess.  A plausible-looking string near a key is not a naming; a
demangled C++ symbol that contains the right class is.  If the search finds
nothing, that is a real answer and gets recorded as one, because "the semantics
are not recoverable from the shipped artefacts" is worth knowing before anyone
writes to a camera.

Note on scale: libSysDef.so is 3.3 MB and viewUnified2.so is 14.3 MB, so string
and table scans are cheap.  Disassembly is not, and is only worth doing if a
region is identified first.
"""
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path

ENG = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\engine')

# keys from the documented signature table, as literal on-disk u32
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
    k = struct.unpack('<I', bytes.fromhex(sig[:8]))[0]
    KEYS[k] = sig

TARGET_KEY = struct.unpack('<I', bytes.fromhex('c34c39a7'))[0]
PAL_LO, PAL_HI = 0x4000, 0x4022


def strings(b, minlen=4):
    for m in re.finditer(rb'[\x20-\x7e]{%d,}' % minlen, b):
        yield m.start(), m.group().decode('latin1')


def s1_key_table(b, label):
    print()
    print('=' * 76)
    print('S1  do the property keys appear as a table in %s?' % label)
    print('=' * 76)
    hits = {}
    for k, sig in KEYS.items():
        pat = struct.pack('<I', k)
        offs = []
        s = 0
        while True:
            i = b.find(pat, s)
            if i < 0:
                break
            offs.append(i)
            s = i + 1
        if offs:
            hits[k] = offs
    print('  %d of %d known keys found as u32 constants' % (len(hits), len(KEYS)))
    # which keys appear most -- the most-used properties are likeliest to be
    # in a dispatch table with a name nearby
    ranked = sorted(hits.items(), key=lambda kv: -len(kv[1]))
    for k, offs in ranked[:12]:
        print('    0x%08x %s  %d occurrence(s)  first @0x%08x'
              % (k, KEYS[k], len(offs), offs[0]))
    if not hits:
        print('  none -- the loader does not embed the keys as plain u32s,')
        print('  which suggests it walks a different structure or computes')
        print('  them at runtime.')
        return hits

    # look for a run of keys close together: a table
    print()
    print('  looking for a contiguous key table:')
    best = []
    for k, offs in hits.items():
        for o in offs:
            # how many other known keys within 64 bytes of this one?
            near = sum(1 for k2, o2 in hits.items() for x in o2
                       if 0 < abs(x - o) <= 64 and k2 != k)
            if near >= 3:
                best.append((near, o, k))
    best.sort(reverse=True)
    for near, o, k in best[:8]:
        print('    @0x%08x  0x%08x (%s)  with %d other keys within 64 B'
              % (o, k, KEYS[k], near))
    if not best:
        print('    no cluster found. Keys are scattered, so there is no')
        print('    single registry table to read names from.')
    return hits


def s2_rtti(b, label):
    print()
    print('=' * 76)
    print('S2  RTTI and mangled C++ symbols in %s' % label)
    print('=' * 76)
    m = re.findall(rb'_Z[A-Za-z0-9_]{4,80}', b)
    print('  _Z-prefixed symbols: %d' % len(m))
    if m:
        seen = {}
        for s in m:
            seen.setdefault(s.decode('latin1'), 0)
            seen[s.decode('latin1')] += 1
        # demangle by hand the common shapes
        for s in sorted(seen)[:40]:
            print('    %s' % s)
    # also the Itanium typeinfo marker
    ti = b.count(b'8typeinfo')
    n1 = b.count(b'N8Jiritsu')
    n2 = b.count(b'Widget')
    n3 = b.count(b'View')
    print()
    print('  "8typeinfo" occurrences: %d' % ti)
    print('  "N8Jiritsu"           : %d' % n1)
    print('  "Widget"              : %d' % n2)
    print('  "View"                : %d' % n3)
    return m


def s3_readable(b, label, near_offsets=()):
    print()
    print('=' * 76)
    print('S3  readable strings in %s' % label)
    print('=' * 76)
    all_s = list(strings(b, 5))
    print('  %d printable runs of 5+ chars' % len(all_s))
    interesting = re.compile(
        r'visible|enabl|select|focus|state|style|color|colour|alpha|'
        r'widget|layout|property|property_|uxc|global\.xdb|'
        r'palette|id_|colorId|styleId|attr', re.I)
    hits = [(o, t) for o, t in all_s if interesting.search(t)]
    print('  %d match UI/format vocabulary' % len(hits))
    for o, t in hits[:60]:
        print('    @0x%08x  %s' % (o, t[:100]))
    if len(hits) > 60:
        print('    ... and %d more' % (len(hits) - 60))
    return hits


def s4_palette_neighbourhood(b, label):
    print()
    print('=' * 76)
    print('S4  the palette table in %s -- what sits beside it?' % label)
    print('=' * 76)
    # find runs of 4-aligned u16 in the palette range
    runs = []
    cur = []
    for o in range(0, len(b) - 1, 4):
        v = struct.unpack_from('<H', b, o)[0]
        if PAL_LO <= v <= PAL_HI:
            cur.append((o, v))
        else:
            if len(cur) >= 8:
                runs.append(cur)
            cur = []
    if len(cur) >= 8:
        runs.append(cur)
    print('  runs of 8+ consecutive palette-range u16: %d' % len(runs))
    for r in runs[:6]:
        print('    @0x%08x  len %d  values %s'
              % (r[0][0], len(r), ' '.join('0x%04x' % v for _o, v in r[:16])))
        # strings within 4 KB of the run
        lo = max(0, r[0][0] - 4096)
        hi = min(len(b), r[0][0] + 4096)
        near = [(o, t) for o, t in strings(b[lo:hi], 5)]
        if near:
            print('      strings within 4 KB: %d, first few:' % len(near))
            for o, t in near[:12]:
                print('        @0x%08x  %s' % (lo + o, t[:80]))
    return runs


def main():
    for name in ('libSysDef.so', 'viewUnified2.so'):
        p = ENG / name
        if not p.exists():
            print('missing %s' % p)
            continue
        b = p.read_bytes()
        print('#' * 76)
        print('# %s  (%d bytes)' % (name, len(b)))
        print('#' * 76)
        s1_key_table(b, name)
        s2_rtti(b, name)
        s3_readable(b, name)
        s4_palette_neighbourhood(b, name)
        print()


if __name__ == '__main__':
    main()
