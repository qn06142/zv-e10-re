"""Is dumps/av-cam.bin really vanilla?

The check 'the three patch sites WE found are unmodified' is circular: the mod
someone flashed almost certainly patches different offsets. So compare against
artefacts that were captured at dump time, not derived by us.
"""
import hashlib
import re
from pathlib import Path

D = Path(r'D:\02_Development_And_Projects\pmca-re\dumps')
PART = D / 'nflasha3_system.bin'
AV = D / 'av-cam.bin'
BAK = D / 'av-cam.bin.bak'
N = 17_289_388


def md5(b):
    return hashlib.md5(b).hexdigest()


def load(p):
    b = p.read_bytes()
    print('  %-34s %10d B  md5 %s' % (p.name, len(b), md5(b)))
    return b


print('=== md5 of the av-cam candidates in dumps/ ===')
av = load(AV)
bak = load(BAK) if BAK.exists() else None
part = load(PART)
print()

# --- locate av-cam inside the raw partition image -----------------------
print('=== locating av-cam inside the raw nflasha3 capture ===')
offs = [m.start() for m in re.finditer(b'ORIL', part)]
print('  ORIL magic occurrences in partition: %d  (first few: %s)' %
      (len(offs), [hex(o) for o in offs[:6]]))
# the ORIL header is 4 bytes preamble then magic, so magic is at +4
offs = [o - 4 for o in offs if o >= 4]
cands = [o for o in offs if o + N <= len(part)]
print('  offsets where a full %d-byte image would fit: %s'
      % (N, [hex(o) for o in cands[:8]]))

region = None
for o in cands:
    seg = part[o:o + N]
    if len(seg) == N and seg[:8] == b'\x0a\x00\x00\xeaORIL':
        region = (o, seg)
        print('  -> exact ORIL image at 0x%08x' % o)
        break
if region is None and cands:
    o = cands[0]
    region = (o, part[o:o + N])
    print('  -> using first fit at 0x%08x (no clean preamble)' % o)
print()


def diff(label, a, b, cap=400):
    """List every differing offset between two equal-length blobs."""
    if len(a) != len(b):
        print('  %s: LENGTH MISMATCH %d vs %d' % (label, len(a), len(b)))
        return []
    d = [i for i in range(len(a)) if a[i] != b[i]]
    print('  %s: %d differing byte(s)%s' %
          (label, len(d), '' if len(d) <= cap else ' (showing first %d)' % cap))
    for i in d[:cap]:
        print('     0x%08x  %02x -> %02x' % (i, a[i], b[i]))
    return d


if region is not None:
    print('=== raw flash capture  vs  dumps/av-cam.bin ===')
    d1 = diff('flash vs av-cam.bin', region[1], av)
    print()

if bak is not None:
    print('=== av-cam.bin.bak  vs  dumps/av-cam.bin ===')
    d2 = diff('bak vs av-cam.bin', bak, av)
    print()

# --- is there a second, independent vanilla reference? -------------------
print('=== other av-cam copies on this PC ===')
for p in Path('D:\\02_Development_And_Projects').rglob('av-cam*.bin'):
    try:
        if p.stat().st_size != N:
            continue
        h = md5(p.read_bytes())
        tag = 'SAME as dumps/av-cam.bin' if h == md5(av) else 'differs'
        print('  %-58s md5 %s  %s' % (str(p)[-58:], h, tag))
    except Exception as e:
        print('  %-58s (unreadable: %s)' % (str(p)[-58:], e))
