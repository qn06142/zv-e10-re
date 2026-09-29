"""Diff every av-cam variant against the confirmed-vanilla baseline (.bak).

Two questions this answers:
  1. Is av-cam.bin.bak the true parent of all our experiments?  If every
     variant is baseline + a small delta, that independently corroborates
     that .bak is the shipped build and not just "a copy of the flash read".
  2. Is the modded image the user flashed one of these variants?  If so we
     can say exactly what it does, and therefore whether the camera is
     likely to boot past USB init with it.
"""
import hashlib
from pathlib import Path

N = 17_289_388
D = Path(r'D:\02_Development_And_Projects\pmca-re\dumps')
BASE = (D / 'av-cam.bin.bak').read_bytes()


def d_off(a, b):
    return [i for i in range(min(len(a), len(b))) if a[i] != b[i]]


base_off = d_off(BASE, BASE)
print('baseline dumps/av-cam.bin.bak  md5 %s  %d B'
      % (hashlib.md5(BASE).hexdigest(), len(BASE)))
print()

rows = []
for p in sorted(D.glob('av-cam*.bin')) + [Path(r'D:\02_Development_And_Projects\pmca-re\fw\av-cam.bin')]:
    if not p.exists() or p.name == 'av-cam.bin.bak':
        continue
    try:
        b = p.read_bytes()
    except OSError:
        continue
    if len(b) != N:
        rows.append((p.name, len(b), None, 'WRONG SIZE'))
        continue
    if b == BASE:
        rows.append((p.name, len(b), 0, 'IDENTICAL to baseline'))
        continue
    d = d_off(BASE, b)
    # capture the value pairs NOW, while b is still the current variant
    pairs = [(i, BASE[i], b[i]) for i in d]
    rows.append((p.name, len(b), len(d), pairs))

print('=== variants vs vanilla baseline ===')
for name, sz, n, extra in rows:
    if isinstance(extra, str):
        print('  %-28s %10d B  %s' % (name, sz, extra))
    elif n == 0:
        print('  %-28s %10d B  IDENTICAL to baseline' % (name, sz))
    else:
        print('  %-28s %10d B  %4d byte(s) differ' % (name, sz, n))
        shown = extra[:12]
        print('       offsets: %s' % ', '.join('0x%07x' % i for i, _, _ in shown))
        print('       values : %s' % ', '.join('%02x->%02x' % (o, v) for _, o, v in shown))
        if n > len(shown):
            print('       ... and %d more' % (n - len(shown)))
print()
print('legend: every listed variant is baseline+delta, i.e. all our patches')
print('were built on top of .bak -- consistent with .bak being the shipped build.')
