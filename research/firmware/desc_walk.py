"""Walk the s4 descriptor list and classify every pointer it contains.

Established:
  * s4 (/dev/stream @ 0x228B2000) is a DESCRIPTOR TABLE, not pixels: the head
    holds kernel VAs and an 0xFFFFFFFF terminator, and re-dumping after a 0xFF
    poke came back 99.8% identical (only live heap pointers moved), so the UI
    redraws it -- it is not the panel scanout.
  * The linear map is confirmed: desc VA 0x828B2000 -> PA 0x028B2000 reads
    back valid ARM CODE (0xE9DB6B77 = ldrb r3,[r11,#-0x24]!).  So
    PA = VA - 0x80000000 for this range.
  * That means 0x8297E300 is a function pointer too, not a buffer, and the
    0x00200000 next to it is a size field for something else.

So: enumerate EVERY plausible pointer in the descriptor region, translate it,
and classify what it points at (code / data / zeros).  A framebuffer stands out
because it is large, has a raster pitch, and is not executable-looking.
"""
import struct
from collections import Counter
from pathlib import Path

S4 = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\s4.bin').read_bytes()[8:]
DESC = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\desc.bin').read_bytes()
FBA = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\fbA.bin').read_bytes()
PAGE_OFF = 0x80000000


def to_pa(va):
    return (va - PAGE_OFF) & 0xFFFFFFFF


print('=== every 32-bit word in the s4 head that looks like a kernel VA ===')
print('    (0x80000000..0x8FFFFFFF -> PA = VA - 0x80000000)')
rows = []
for i in range(0, 0x400, 4):
    v = struct.unpack_from('<I', S4, i)[0]
    if 0x80000000 <= v < 0x90000000:
        rows.append((i, v, to_pa(v)))
uniq = {}
for off, va, pa in rows:
    uniq.setdefault(pa, []).append(off)
print('  %d VA words, %d distinct PAs' % (len(rows), len(uniq)))
for pa in sorted(uniq):
    print('    PA 0x%08x   from %s' % (pa, ', '.join('+0x%02x' % o for o in uniq[pa])))
print()

# What is at each of those PAs?  We only sampled two, so classify what we have
# and identify which VA range they came from.
print('=== classify the two PAs we sampled ===')
for label, data, va in (('0x0297E300', FBA, 0x8297E300),
                        ('0x028B2000', DESC, 0x828B2000)):
    h = Counter(data)
    zeros = h.get(0, 0) / len(data)
    w0, w1 = struct.unpack_from('<II', data, 0)
    # ARM code heuristics: a function often starts with push/stmdb, and the
    # first word having a plausible condition field is weak, so use the
    # strongest signal available: does it look like a repeating 4-byte stride
    # of similar words (table) or varied code?
    print('  %s  first word 0x%08X  zeros %.1f%%  distinct %d' % (label, w0, 100 * zeros, len(h)))
    print('     %s' % data[:24].hex(' '))
print()

print('=== the descriptor head, annotated ===')
for i in range(0, 0x70, 4):
    v = struct.unpack_from('<I', S4, i)[0]
    note = ''
    if v == 0xFFFFFFFF:
        note = 'TERMINATOR'
    elif 0x80000000 <= v < 0x90000000:
        note = 'VA -> PA 0x%08x' % to_pa(v)
    elif v == 0x00200000:
        note = 'SIZE 2 MB'
    elif v in (0,):
        note = 'null'
    print('  +0x%02x  0x%08X  %s' % (i, v, note))
print()

print('=== does 0x00200000 appear next to other size-like values? ===')
sizes = []
for i in range(0, 0x2000, 4):
    v = struct.unpack_from('<I', S4, i)[0]
    if 0x10000 <= v <= 0x4000000 and (v & 0xFFF) == 0:
        sizes.append((i, v))
print('  %d page-aligned values in 64K..64M:' % len(sizes))
seen = set()
for i, v in sizes:
    if v in seen:
        continue
    seen.add(v)
    print('    +0x%04x  0x%08x  (%d KB)' % (i, v, v // 1024))
