"""The panel brightness LUT at file 0x0087D7E2.

SetPanelBrightness::Execute (0x00150BA8) does:
    ldrb  r2, [r5, #1]                     ; brightness value (index)
    ldr   r3, [pc, #0x378] ; add r3, pc     ; -> 0x0087D7E2
    ldr.w r3, [r3, r2, lsl #2]              ; curve = table[brightness]
    str   r3, [sp, #0x18]
    strb  r3, [sp, #0x21]

If that table is writable, editing it changes panel brightness with no code
execution at all -- the firmware's own path, a data patch, trivially
reversible.  This script confirms the table's shape, extent and writability
before anyone touches the flash.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

av = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
N = len(av)
BASE = 0x635C6000

T = 0x0087d7e2

print('=== 16 words before the table (0x%08x) ===' % (T - 64))
for o in range(T - 64, T, 4):
    v = struct.unpack_from('<I', av, o)[0]
    print('  0x%08x  0x%08x  %10d' % (o, v, struct.unpack_from('<i', av, o)[0]))

print()
print('=== 64 words AT the table (0x%08x) ===' % T)
prev = None
for k in range(64):
    o = T + 4 * k
    v = struct.unpack_from('<I', av, o)[0]
    s = struct.unpack_from('<i', av, o)[0]
    d = '' if prev is None else ('%+d' % (s - prev))
    print('  [%2d] 0x%08x  0x%08x  %10d  %s' % (k, o, v, s, d))
    prev = s

print()
print('=== is this a plausible curve? monotonic / small range? ===')
vals = [struct.unpack_from('<I', av, T + 4 * k)[0] for k in range(256)]
nz = [v for v in vals if v]
print('  256 entries, %d non-zero, min=%d max=%d' % (len(nz), min(vals), max(vals)))
mono = all(vals[i] <= vals[i + 1] for i in range(255))
print('  monotonic non-decreasing: %s' % mono)
print('  all < 0x10000 (u16-like): %s' % all(v < 0x10000 for v in vals))
print('  first 24: %s' % vals[:24])
print()
print('  unique values: %d  -> %s' % (len(set(vals)), sorted(set(vals))[:16]))

print()
print('=== how big is the table before it stops looking like a curve? ===')
run = 0
for k in range(1024):
    v = struct.unpack_from('<I', av, T + 4 * k)[0]
    if v < 0x10000:
        run = k + 1
    else:
        break
print('  %d consecutive plausible entries (0x%x bytes)' % (run, run * 4))

print()
print('=== section placement: is the file an ELF we can check for .data? ===')
print('  magic: %s' % av[:8].hex(' '))
print('  ELF?  %s' % (av[:4] == b'\x7fELF'))
print('  size %d (0x%X)' % (N, N))
print('  table at 0x%08X is %.1f%% into the image'
      % (T, 100.0 * T / N))
print()
print('=== for reference, where is the string/code/data boundary? ===')
# the signature strings sat at 0x0098xxxx; the code ran to at least 0x0018xxxx
print('  last Execute/Activate signature string ~ 0x00989xxx')
print('  this table at 0x0087D7E2 is BELOW that -> inside the code/rodata span,')
print('  so writability is NOT yet established.  Must confirm before patching.')
