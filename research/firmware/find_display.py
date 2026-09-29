"""Find the display controller by its MMIO base constants in the front end.

The decoder has no CPU-side pixel array - SFMC output goes to DDR and is
DMA'd out by APL/XDMAC.  So the only thing we can write to that reaches the
glass is the display controller's own registers.

iomem showed the peripheral map is:
    c0000000-e7ffffff  PCIe0
    e8000000-efffffff  PCIe1
    f0200000-f02fffff  dwc3.0
    f2000000-f2000fff  uart0
and conspicuously did NOT list a display controller, so it is either in the
unlisted 0x40000000-0x7fffffff window or simply not described.

Method: harvest every 32-bit constant in the front-end ELF that looks like a
peripheral address, cluster them, and see which cluster sits in code that also
references display-ish strings.
"""
import re
import struct
from collections import defaultdict
from pathlib import Path

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
FE = BASE / 'dumps' / 'camera_2025' / 'usr_lib_raw' / 'elf_05610c00.so'

b = FE.read_bytes()
N = len(b)
print('front end %s: %d bytes' % (FE.name, N))
print()

# peripheral-ish ranges
RANGES = [
    (0xC0000000, 0xEFFFFFFF, 'PCIe'),
    (0xF0000000, 0xFFFFFFFF, 'other MMIO'),
    (0x40000000, 0x7FFFFFFF, 'unlisted 0x4-0x7 window'),
    (0xE0000000, 0xEFFFFFFF, '0xE0-0xEF'),
]

hits = defaultdict(list)
for i in range(0, N - 4, 4):
    v = struct.unpack_from('<I', b, i)[0]
    for lo, hi, name in RANGES:
        if lo <= v <= hi:
            # keep only page-aligned-ish bases, not incidental code values
            if (v & 0xFFF) == 0 or (v & 0xFFFF) == 0:
                hits[name].append((i, v))
            break

print('=== peripheral-looking constants, page/16K-aligned ===')
for name, lst in hits.items():
    vals = sorted({v for _, v in lst})
    print('  %-24s %4d occurrence(s), %d distinct, e.g. %s' % (
        name, len(lst), len(vals), ' '.join('0x%08x' % v for v in vals[:10])))
print()

# which 0xF0.. region clusters look like a display controller?
print('=== 0xF0000000-0xFFFFFFFF bases, grouped by 64KB block ===')
f0 = sorted({v for _, v in hits.get('other MMIO', [])})
blocks = defaultdict(list)
for v in f0:
    blocks[v >> 16].append(v)
for blk in sorted(blocks):
    vs = blocks[blk]
    print('  0x%08x..0x%08x  %d base(s): %s' % (
        blk << 16, (blk << 16) | 0xFFFF, len(vs),
        ' '.join('0x%08x' % v for v in vs[:6])))
print()

print('=== 0x4xxxxxxx bases in the unlisted window, grouped by 1MB ===')
u = sorted({v for _, v in hits.get('unlisted 0x4-0x7 window', [])})
mb = defaultdict(list)
for v in u:
    mb[v >> 20].append(v)
for blk in sorted(mb):
    vs = mb[blk]
    print('  0x%07x00000  %d base(s): %s' % (blk, len(vs),
                                             ' '.join('0x%08x' % v for v in vs[:6])))
print()

# display strings, for cross-reference
print('=== display-related strings in the front end ===')
disp = []
for m in re.finditer(rb'[\x20-\x7e]{5,90}', b):
    s = m.group().decode('latin1')
    if re.search(r'\b(lcd|display|panel|disp_|backlight|bl_|dcr|tcon|oled|lvds|mipi)\b',
                 s, re.I):
        disp.append((m.start(), s))
print('  %d matching strings' % len(disp))
for off, s in disp[:40]:
    print('  0x%08x  %s' % (off, s[:80]))
