"""Disassemble the ldec driver object found via the s4 descriptor.

Path that got here:
  s4 (/dev/stream @ 0x228B2000) is a DESCRIPTOR TABLE (re-dump after a 0xFF
  poke was 99.8% identical -> the UI redraws it, so it is not the panel
  scanout).  Its head holds kernel VAs.  The linear map is confirmed:
  VA 0x828B2000 -> PA 0x028B2000 reads back valid ARM code
  (0xE9DB6B77 = ldrb r3, [r11, #-0x24]!).

  The +0x38..+0x134 region is pairs of IDENTICAL VAs (0x828B2030, 0x828B2030,
  0x828B2038, 0x828B2038, ...) which is a vtable: each entry listed twice.
  That makes 0x028B2000 a device object whose methods live in the ldec driver.

Rather than guess which field is the buffer, read the driver: find the code that
hands a surface to the panel, i.e. the function that writes a source address
into a panel/DMA register.  The ioctl numbers and that store tell us both the
control path and the buffer address.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from thumb import mkdis, dis1, walk, calls_of                              # noqa: E402

DESC = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\desc.bin').read_bytes()
FBA = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\fbA.bin').read_bytes()
md = mkdis()


def dis_at(buf, file_off, va, n=40):
    out = []
    for i in dis_all(buf, file_off, va, n):
        out.append(i)
    return out


def dis_all(buf, off, va, n):
    a = off
    while len(_acc) < n and a + 4 <= len(buf):
        i = dis1(md, buf[a:a + 4], va + (a - off))
        if i is None:
            a += 2
            continue
        _acc.append(i)
        a += i.size
    return _acc


print('=== the device object at PA 0x028B2000 (VA 0x828B2000) ===')
_acc = []
base_off, base_va = 0, 0x828B2000
for i in dis_all(DESC, base_off, base_va, 48):
    print('  0x%08x  %-12s %-9s %s' % (i.address, i.bytes.hex(' '), i.mnemonic, i.op_str))
print()

# The vtable pairs in s4 point at consecutive addresses 8 bytes apart, which
# is the stride of 32-bit ARM code? No -- 8 bytes = two instructions.  Check
# whether those are code by reading a couple of them.
S4 = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\s4.bin').read_bytes()[8:]
vas = []
for i in range(0x38, 0x138, 4):
    v = struct.unpack_from('<I', S4, i)[0]
    if 0x80000000 <= v < 0x90000000 and v not in vas:
        vas.append(v)
vas.sort()
print('=== distinct VAs in the vtable-like region: %d ===' % len(vas))
print('  first: %s' % ['0x%08X' % v for v in vas[:8]])
print('  deltas: %s' % [vas[i + 1] - vas[i] for i in range(min(8, len(vas) - 1))])
print()

# Those VAs are 0x828B2030..0x828B2128, i.e. PA 0x028B2030.., which is 0x30
# into the 256 KB we already read.  Disassemble there.
print('=== code at PA 0x028B2030 (VA 0x828B2030) -- first vtable entry ===')
_acc = []
for i in dis_all(DESC, 0x30, 0x828B2030, 24):
    print('  0x%08x  %-12s %-9s %s' % (i.address, i.bytes.hex(' '), i.mnemonic, i.op_str))
print()

# The vtable spans 0x828B2030..0x828B2128 = 0xF8 bytes = 62 words.  Treat it as
# a table of function pointers, not code, and check: do those words look like
# code (small odd/even patterns) or like more pointers?
print('=== is 0x028B2030 code or more pointers? ===')
w = [struct.unpack_from('<I', DESC, 0x30 + 4 * i)[0] for i in range(16)]
for i, v in enumerate(w):
    tag = ''
    if 0x80000000 <= v < 0x90000000:
        tag = ' -> looks like a POINTER (VA)'
    elif (v & 0xF) in (0, 4, 8, 0xC):
        tag = '  plausible ARM code word'
    print('   [%2d] 0x%08X%s' % (i, v, tag))
print()

print('=== search DESC+FBA for MMIO-looking constants (panel registers) ===')
import re                                              # noqa: E402
seen = {}
for label, buf, va0 in (('desc', DESC, 0x828B2000), ('fbA', FBA, 0x8297E300)):
    for off in range(0, len(buf) - 4, 4):
        v = struct.unpack_from('<I', buf, off)[0]
        if 0xF0000000 <= v <= 0xFFFFFFFF or 0xC0000000 <= v <= 0xCFFFFFFF:
            seen.setdefault(v, []).append((label, off))
print('  %d distinct peripheral-range constants' % len(seen))
for v in sorted(seen)[:30]:
    locs = seen[v][:3]
    print('    0x%08X  x%-3d  e.g. %s' % (v, len(seen[v]),
                                         ', '.join('%s+0x%x' % l for l in locs)))
