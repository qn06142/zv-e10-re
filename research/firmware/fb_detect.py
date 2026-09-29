"""Is /tmp/fb*.bin actually a framebuffer?  (pure Python, no numpy)

Candidates, from the UI engine's mmap table:
    fb0  0x20312000   2 MB /dev/stream mapping
    fb1  0x3F7ED000   2 MB /dev/stream mapping
    fb2  0x3E753000   mapped TWICE by the UI, r--s then rw-s

Decisive test: ROW PITCH.  In a framebuffer consecutive rows are exactly
width*bpp bytes apart, so mean |a[i] - a[i+stride]| has a sharp minimum at
the correct stride.  Code, logs and ring buffers have no such structure.

Sampling rather than full scans keeps this pure-Python: 1500 deterministic
positions per stride is ample to expose a correlation minimum.
"""
from collections import Counter
from pathlib import Path

D = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera')
NAMES = [('fb0', 0x20312000), ('fb1', 0x3F7ED000), ('fb2', 0x3E753000)]
NS = 1500


def pitch_scan(a):
    """(meandiff, stride) minimised over sampled positions."""
    n = len(a)
    out = []
    for s in range(64, min(4097, n)):
        step = max(1, (n - s) // NS)
        tot = 0
        c = 0
        for i in range(0, n - s, step):
            d = a[i] - a[i + s]
            tot += d if d >= 0 else -d
            c += 1
        out.append((tot / c, s))
    out.sort()
    return out


for name, phys in NAMES:
    p = D / (name + '.bin')
    if not p.exists():
        print('%s MISSING' % name)
        continue
    a = p.read_bytes()
    hist = Counter(a)
    zeros = hist.get(0, 0) / len(a)
    nz = [v for v in a if v != 0]
    mean = sum(a) / len(a)
    var = sum((v - mean) ** 2 for v in a) / len(a)
    print('=== %s  phys 0x%08x  %d bytes ===' % (name, phys, len(a)))
    print('  zeros %.1f%%  distinct %d/256  mean %.1f  std %.1f'
          % (zeros * 100, len(hist), mean, var ** 0.5))
    if zeros > 0.995:
        print('  -> all zero: not a live buffer\n')
        continue

    res = pitch_scan(a)
    base = dict((s, m) for m, s in res).get(64)
    print('  baseline meandiff at stride 64: %.3f' % base)
    print('  lowest strides:')
    for m, s in res[:8]:
        print('     stride %5d (0x%04x)  meandiff %.3f' % (s, s, m))
    m0, s0 = res[0]
    ratio = base / m0 if m0 > 0 else 999
    if ratio > 3.0:
        print('  -> SHARP MINIMUM at stride %d (%.1fx below baseline): IMAGE-LIKE'
              % (s0, ratio))
    elif ratio > 1.5:
        print('  -> moderate minimum at stride %d (%.2fx): weak structure'
              % (s0, ratio))
    else:
        print('  -> no pitch structure: NOT a framebuffer')
    print()

print('=== render the best candidate ===')
for name, phys in NAMES:
    p = D / (name + '.bin')
    if not p.exists():
        continue
    a = p.read_bytes()
    if len(a) < 8192:
        continue
    res = pitch_scan(a)
    base = dict((s, m) for m, s in res).get(64)
    m0, s0 = res[0]
    if base / m0 < 1.5:
        print('%s: no structure, nothing to render' % name)
        continue
    for bpp in (2, 1, 4):
        if s0 % bpp:
            continue
        w = s0 // bpp
        rows = len(a) // s0
        if w < 32 or rows < 8:
            continue
        print('\n--- %s: stride %d -> %d x %d, %d byte(s)/px ---'
              % (name, s0, w, rows, bpp))
        ramp = ' .:-=+*#%@'
        cstep = max(1, w // 72)
        rstep = max(1, rows // 28)
        for r in range(0, rows, rstep):
            line = []
            for c in range(0, w, cstep):
                v = a[r * s0 + c * bpp]
                line.append(ramp[min(9, v * 10 // 256)])
            print('   |%s|' % ''.join(line))
        break
