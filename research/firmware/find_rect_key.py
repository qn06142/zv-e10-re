"""Does the arity-4 key appear in the view files, and does it carry four values?

The chain so far
----------------
1. c34c39a70111 was named "caution" from code: a strict ==1 predicate inside the
   exported symbol ViewCautionToInstance.
2. The four functions previously called deserialisers are constructors: base
   ctor, install vtable, zero the payload.  They never read the stream.
3. So the number of payload fields a constructor zeroes is the property's arity.
   Census of the whole engine: exactly one arity-4 class, constructor 0x677010,
   fields at 0x14/0x18/0x1c/0x20, and exactly one key -- 0x325cf838.

That is a rect on the engine side.  This script asks the only question that
matters now: is it a rect in the files too, and where.

Why the search is a prefix search
---------------------------------
The engine carries the key as a 32-bit constant, which is only the first four
bytes of the six-byte on-disk key.  Verified on the three known keys:

    c3 4c 39 a7 | 01 11   ->  0xa7394cc3
    1f 02 80 55 | 02 08   ->  0x5580021f
    ed 18 8f 1a | 01 8d   ->  0x1a8f18ed

The first four bytes are the little-endian constant; the last two are not in the
code at all.  So the arity-4 key is known only as the prefix 38 f8 5c 32, and
the trailing two bytes have to be read off the file.  Searching for all six
would have returned nothing and looked like a refutation.

Controls, because six earlier searches could not fail
-----------------------------------------------------
  P1  Positive control.  The same search, same code, for the three known
      four-byte prefixes.  Each must be found in the view files, and the byte
      that follows must be the one the code does not carry.  If the known keys
      are absent, the search is broken and the arity-4 result means nothing.
  P2  Chance rate.  How often does a random four-byte prefix occur at all?  With
      299 files the count alone proves nothing, so the expected number of
      incidental hits is computed and shown next to the observed count.
  P3  The record shape.  A hit is only interesting if four plausible values
      follow.  Values are printed and judged, not scored by a formula, because
      the last four geometry attempts each had a formula that could not fail.
"""
import struct
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share\app')

# (name, 4-byte on-disk prefix, 2 trailing bytes known from earlier work)
KNOWN = [
    ('c34c39a70111  bool/caution', b'\xc3\x4c\x39\xa7', b'\x01\x11'),
    ('1f0280550208  3 word fields', b'\x1f\x02\x80\x55', b'\x02\x08'),
    ('ed188f1a018d  2 fields',      b'\xed\x18\x8f\x1a', b'\x01\x8d'),
    ('1b572204010e  2 fields',      b'\x1b\x57\x22\x04', b'\x01\x0e'),
]
TARGET = b'\x38\xf8\x5c\x32'          # the arity-4 / rect key prefix


def load():
    files = sorted(ROOT.glob('*.uxc'))
    return files, {f.name: f.read_bytes() for f in files}


def find_all(blobs, pat):
    out = []
    for name, b in blobs.items():
        i = 0
        while True:
            i = b.find(pat, i)
            if i < 0:
                break
            out.append((name, i))
            i += 1
    return out


def main():
    files, blobs = load()
    total = sum(len(b) for b in blobs.values())
    print('=== the view corpus ===')
    print('  %d files, %d bytes' % (len(files), total))
    print()

    # ---------------- P1  positive control ----------------------------------
    print('=== P1  positive control: do the known keys appear? ===')
    print()
    ctrl_ok = True
    for name, pre, tail in KNOWN:
        hits = find_all(blobs, pre)
        exact = [h for h in hits if blobs[h[0]][h[1] + 4:h[1] + 6] == tail]
        print('  %-28s prefix hits %5d   full 6-byte hits %5d'
              % (name, len(hits), len(exact)))
        if not exact:
            ctrl_ok = False
    print()
    print('  control %s' % ('PASSED' if ctrl_ok else 'FAILED -- search is broken'))
    print()

    # ---------------- the target --------------------------------------------
    print('=== the arity-4 key, prefix 38 f8 5c 32 ===')
    hits = find_all(blobs, TARGET)
    print('  hits: %d' % len(hits))
    byfile = Counter(n for n, _ in hits)
    print('  in %d distinct files' % len(byfile))
    print()

    # ---------------- P2  chance rate ---------------------------------------
    print('=== P2  chance rate ===')
    # expected incidental hits = total_bytes * 2^-32
    exp = total / 2.0 ** 32
    print('  bytes searched          : %d' % total)
    print('  expected random hits    : %.6f' % exp)
    print('  observed                : %d' % len(hits))
    if len(hits) > 4 * exp + 4:
        print('  >> far above chance')
    else:
        print('  >> consistent with chance; not a finding')
    print()

    # ---------------- P3  the record shape ----------------------------------
    print('=== P3  what follows each hit ===')
    print()
    if not hits:
        print('  no hits, nothing to inspect')
        return
    tails = Counter()
    for n, o in hits:
        tails[blobs[n][o + 4:o + 24]] += 1
    print('  distinct 20-byte tails: %d' % len(tails))
    print()
    for t, c in tails.most_common(8):
        print('  x%-5d  %s' % (c, ' '.join('%02x' % x for x in t)))
    print()
    print('  first 12 hits in full:')
    for n, o in hits[:12]:
        w = blobs[n][o:o + 24]
        print('    %-34s @%06x  %s' % (n, o, ' '.join('%02x' % x for x in w)))
    print()
    # if four values follow, read them as the candidate rect
    print('  reading four 32-bit values after each hit:')
    for n, o in hits[:12]:
        b = blobs[n]
        if o + 20 <= len(b):
            v = struct.unpack_from('<4I', b, o + 4)
            vh = struct.unpack_from('<4H', b, o + 4)
            print('    %-30s @%06x  u32 %s   u16 %s'
                  % (n[:30], o, v, vh))
    print()

    # ---------------- what the bool's own record looks like, for comparison
    print('=== for comparison: the caution bool\'s record in the same files ===')
    print()
    ch = find_all(blobs, b'\xc3\x4c\x39\xa7\x01\x11')
    print('  full-key hits: %d' % len(ch))
    ct = Counter()
    for n, o in ch:
        ct[blobs[n][o:o + 20]] += 1
    for t, c in ct.most_common(6):
        print('  x%-5d  %s' % (c, ' '.join('%02x' % x for x in t)))
    print()
    for n, o in ch[:6]:
        w = blobs[n][o:o + 20]
        print('    %-34s @%06x  %s' % (n, o, ' '.join('%02x' % x for x in w)))
        if o + 12 <= len(blobs[n]):
            print('       after key: u32 %s  u16 %s'
                  % (struct.unpack_from('<3I', blobs[n], o + 6),
                     struct.unpack_from('<5H', blobs[n], o + 6)))


if __name__ == '__main__':
    main()
