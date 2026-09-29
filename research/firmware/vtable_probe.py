"""Why is every vtable member unaligned?

Two candidates:
  (1) the vtable base is off by one slot, so we read the wrong words
  (2) the entries are ARM/Thumb function pointers WITH the low bit set, or
      Itanium ptr-to-member-function (ptr, 1-byte adj) pairs, 8 bytes per slot

Test both by dumping the raw words around one vtable and trying to decode the
neighbouring values under each hypothesis.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from thumb import dis1, mkdis                                              # noqa: E402

BASE = 0x635C6000
av = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
N = len(av)
md = mkdis()

VT = 0x00fbb0f8     # VdfDisplayCmdSetPanelBrightness

print('=== raw words around the vtable 0x%08x ===' % VT)
for k in range(-4, 16):
    off = VT + 4 * k
    if off < 0 or off + 4 > N:
        continue
    v = struct.unpack_from('<I', av, off)[0]
    mark = '   <-- vtable[0]' if k == 0 else ''
    print('  [%+3d] 0x%08x  0x%08x%s' % (k, off, v, mark))
print()

print('=== hypothesis 1: shift the base by one slot ===')
for shift in (-1, 1, 2):
    base = VT + 4 * shift
    print('  base 0x%08x (shift %+d):' % (base, shift))
    for k in range(6):
        v = struct.unpack_from('<I', av, base + 4 * k)[0]
        pf = v - BASE
        ok = 0x1000 <= pf < 0xAED000
        i0 = dis1(md, av[pf:pf + 4], pf) if ok else None
        print('     [%d] 0x%08x  file 0x%08x  %s' % (
            k, v, pf, ('%s %s' % (i0.mnemonic, i0.op_str[:34])) if i0 else '<out of range>'))
    print()

print('=== hypothesis 2: entries carry the Thumb bit ===')
print('  (if bit0 is set on the stored word, mask it and retry)')
for k in range(6):
    v = struct.unpack_from('<I', av, VT + 4 * k)[0]
    print('     [%d] 0x%08x  bit0=%d  masked 0x%08x -> file 0x%08x'
          % (k, v, v & 1, v & ~1, (v & ~1) - BASE))
print()

print('=== what does the typeinfo slot [-1] look like? ===')
print('  vtable[-1] should be the typeinfo runtime address')
ti = struct.unpack_from('<I', av, VT - 4)[0]
print('  word at 0x%08x = 0x%08x   (file 0x%08x)'
      % (VT - 4, ti, ti - BASE if ti >= BASE else 0))
print()
print('  known typeinfo file offset for SetPanelBrightness = 0x00fec548')
print('  so vtable[-1] should be 0x%08x' % (0x00fec548 + BASE))
print('  it is                   0x%08x  %s'
      % (ti, 'MATCH' if ti == 0x00fec548 + BASE else 'MISMATCH'))
print()
print('=== if MISMATCH, the true vtable may be 4 bytes earlier/later ===')
for d in (-4, 4, 8, -8):
    t2 = struct.unpack_from('<I', av, VT + d - 4)[0]
    print('   vtable 0x%08x: [-1] = 0x%08x  %s'
          % (VT + d, t2, 'MATCH' if t2 == 0x00fec548 + BASE else ''))
