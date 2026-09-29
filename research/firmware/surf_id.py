"""Which /dev/stream surface is the panel?

Four surfaces were dumped by mmapping the same offsets the UI engine
(uxengine_res2) maps, then written out with an 8-byte header:
    magic 'ZVD1' | mmap return address | surface bytes

    s2  0x20312000  2 MB
    s3  0x3F7ED000  2 MB
    s4  0x228B2000  2 MB
    s1  0x22312000  4 MB   (known mostly empty)

A framebuffer is identified by its ROW PITCH: mean |a[i] - a[i+stride]| has a
sharp minimum at width*bpp.  A live panel also has a realistic spread of pixel
values -- a UI with text and icons is not 87% zeros with two distinct values.

The comparison across surfaces is the point: whatever the panel looks like, it
should look DIFFERENT from the others, and one of them should look like an
image.
"""
import struct
import sys
from collections import Counter
from pathlib import Path

D = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera')
SURF = [('s2', 0x20312000, 0x200000), ('s3', 0x3F7ED000, 0x200000),
        ('s4', 0x228B2000, 0x200000), ('s1', 0x22312000, 0x400000)]
NS = 1200


def pitch_scan(d, lo=64, hi=4096):
    out = []
    n = len(d)
    for s in range(lo, min(hi + 1, n)):
        step = max(1, (n - s) // NS)
        tot = c = 0
        for i in range(0, n - s, step):
            x = d[i] - d[i + s]
            tot += x if x >= 0 else -x
            c += 1
        out.append((tot / c, s))
    out.sort()
    return out


def describe(name, off, length):
    p = D / (name + '.bin')
    if not p.exists():
        print('%s MISSING' % name)
        return None
    raw = p.read_bytes()
    magic, mmap = struct.unpack_from('<II', raw, 0)
    d = raw[8:]
    print('=== %s  offset 0x%08x  len 0x%X ===' % (name, off, length))
    print('  magic %r   mmap -> 0x%08x   got %d B' % (struct.pack('<I', magic), mmap, len(d)))
    h = Counter(d)
    nz = sum(1 for v in d if v)
    print('  zeros %5.1f%%   distinct %3d/256   mean %5.1f' %
          (100.0 * (len(d) - nz) / len(d), len(h), sum(d) / len(d)))
    print('  top 6: %s' % [(hex(v), c) for v, c in h.most_common(6)])

    res = pitch_scan(d)
    base = dict((s, m) for m, s in res).get(64, 0.0)
    print('  pitch scan: baseline@64 = %.3f' % base)
    for m, s in res[:5]:
        print('     stride %5d (0x%04x)  meandiff %.3f  ratio %.2fx'
              % (s, s, m, base / m if m else 0))
    m0, s0 = res[0]
    ratio = base / m0 if m0 else 0
    verdict = 'IMAGE-LIKE' if ratio > 3 else ('weak structure' if ratio > 1.5 else 'no pitch')
    print('  -> %s (%.2fx)' % (verdict, ratio))
    print()
    return {'name': name, 'off': off, 'zeros': (len(d) - nz) / len(d),
            'distinct': len(h), 'mean': sum(d) / len(d), 'ratio': ratio,
            'stride': s0, 'data': d, 'top': h.most_common(4)}


info = [describe(n, o, l) for n, o, l in SURF]
info = [i for i in info if i]

print('=== summary: which looks most like a rendered panel? ===')
print('  %-4s %-12s %8s %6s %8s %8s' % ('surf', 'offset', '%zeros', 'dist', 'ratio', 'stride'))
for i in sorted(info, key=lambda x: -x['ratio']):
    print('  %-4s 0x%08x  %7.1f%% %6d %7.2fx %8d'
          % (i['name'], i['off'], 100 * i['zeros'], i['distinct'], i['ratio'], i['stride']))

# A real panel is neither near-empty nor two-valued.  Flag anything that is
# actually a usable image: low zero fraction AND a wide value spread.
print()
for i in info:
    if i['zeros'] < 0.5 and i['distinct'] > 32 and i['ratio'] > 2.0:
        print('  CANDIDATE: %s at 0x%08x' % (i['name'], i['off']))
