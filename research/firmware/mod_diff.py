"""What did the mod actually change?

vanilla = dumps/av-cam.bin.bak          (md5 cdcae9d4...)
modded  = F:/restore/av-cam.modded.bin  (md5 3c883661...)

The user's report: the ONLY regression was video playback. Everything else
worked. So the diff should be small and should land in code that the
playback path uses and the rest of the camera does not.
"""
import hashlib
from pathlib import Path

N = 17_289_388
VAN = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak')
MOD = Path(r'F:\restore\av-cam.modded.bin')

a = VAN.read_bytes()
b = MOD.read_bytes()
print('vanilla  %d B  md5 %s' % (len(a), hashlib.md5(a).hexdigest()))
print('modded   %d B  md5 %s' % (len(b), hashlib.md5(b).hexdigest()))
assert len(a) == len(b) == N, 'size mismatch - not a byte-level patch'
print()

# every differing byte
diff = [i for i in range(N) if a[i] != b[i]]
print('=== total differing bytes: %d ===' % len(diff))
if not diff:
    raise SystemExit('identical - nothing to explain')

# group into contiguous runs
runs = []
s = diff[0]
p = diff[0]
for i in diff[1:]:
    if i == p + 1:
        p = i
    else:
        runs.append((s, p + 1))
        s = i
        p = i
runs.append((s, p + 1))

print('=== grouped into %d contiguous run(s) ===' % len(runs))
for st, en in runs:
    print()
    print('  RUN 0x%08x .. 0x%08x   (%d bytes)' % (st, en, en - st))
    print('    vanilla: %s' % a[st:en].hex(' '))
    print('    modded : %s' % b[st:en].hex(' '))
    lo = max(0, st - 16)
    hi = min(N, en + 16)
    print('    context vanilla %s' % a[lo:hi].hex(' '))
    print('    with ^ marking the run: %s' % (
        a[lo:st].hex(' ') + '[' + a[st:en].hex(' ') + ']' + a[en:hi].hex(' ')))

print()
print('=== summary table ===')
print('  %-12s %-8s %s' % ('offset', 'len', 'delta'))
for st, en in runs:
    d = ' '.join('%02x->%02x' % (a[i], b[i]) for i in range(st, min(en, st + 12)))
    if en - st > 12:
        d += ' ...'
    print('  0x%08x  %-8d %s' % (st, en - st, d))
