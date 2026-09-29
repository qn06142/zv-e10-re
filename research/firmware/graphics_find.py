"""Find the display/graphics engine driver in av-cam.bin.

The user is right that the pixels need not be CPU-visible. Evidence:
    0x6AA00000  - a single-byte CPU read HANGS the session => hardware aperture
    wbi_cmpr.waddr=0x6AA00000 wsize=0x100000 nbuf=12   12 x 1MB descriptors
    XDMAC (DMA engine), HME_COPY_SRC_ADDR, cp_import...canvas[%dx%d]
    apl_mov_set_aic R0/R1/R2 W0/W1/W2 with (DDR)/(eSRAM) variants

So: locate the code that programs those descriptors, and the register maps
it writes.  That is the only way to reach the display on this device.
"""
import re
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from thumb import mkdis, dis1, decode_movw                                  # noqa: E402

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
av = (BASE / 'dumps' / 'av-cam.bin.bak').read_bytes()
N = len(av)
md = mkdis()

print('=== strings naming the graphics/display engine ===')
PAT = re.compile(
    r'(HME_[A-Z0-9_]+|cp_import|canvas\[|[Dd]isplay[A-Za-z]*|gpu|GPU|'
    r'tcon|TCON|panel|PANEL|lcdc|LCDC|mipi|MIPI|dcr_|DCR|zima|marble|Marble)')
seen = {}
for m in re.finditer(rb'[\x20-\x7e]{6,140}', av):
    s = m.group().decode('latin1')
    if PAT.search(s):
        seen.setdefault(s[:110], m.start())
for k in sorted(seen, key=lambda x: seen[x]):
    print('  0x%08x  %s' % (seen[k], k))
print('  (%d distinct)' % len(seen))
print()

print('=== MMIO base constants in the 0xF0000000-0xFFFFFFFF band ===')
print('    (iomem only listed dwc3.0 and uart; a display controller would')
print('     be another block there, or in the unlisted 0x4-0x7 window)')
band = defaultdict(int)
for i in range(0, N - 4, 2):
    hw1, hw2 = struct.unpack_from('<HH', av, i)
    v, rd = decode_movw(hw1, hw2)
    if v is None:
        continue
    # movw gives imm16; a full 32-bit base also needs the following movt
    if 0xF000 <= v <= 0xFFFF and rd is not None:
        nxt = decode_movw(*struct.unpack_from('<HH', av, i + 4)) if i + 8 <= N else (None, None)
        if nxt[0] is not None and 0xF000 <= nxt[0] <= 0xFFFF:
            base32 = (nxt[0] << 16) | v
            band[base32] += 1
print('  movw+movt pairs forming 0xFxxx:  %d distinct' % len(band))
for k in sorted(band, key=lambda x: -band[x])[:30]:
    print('    0x%08x  x%d' % (k, band[k]))
print()

print('=== the 0x4xxxxxxx-0x7xxxxxxx window (where av-cam.bin is XIP) ===')
band2 = defaultdict(int)
for i in range(0, N - 4, 2):
    hw1, hw2 = struct.unpack_from('<HH', av, i)
    v, rd = decode_movw(hw1, hw2)
    if v is None:
        continue
    if 0x4F00 <= v <= 0x4FFF and rd is not None:
        nxt = decode_movw(*struct.unpack_from('<HH', av, i + 4)) if i + 8 <= N else (None, None)
        if nxt[0] is not None and 0x0004 <= nxt[0] <= 0x0006:
            band2[(nxt[0] << 16) | v] += 1
print('  distinct 0x4xxxxxxx bases: %d' % len(band2))
for k in sorted(band2, key=lambda x: -band2[x])[:25]:
    print('    0x%08x  x%d' % (k, band2[k]))
print()

print('=== every 32-bit constant in the whole image that looks MMIO ===')
mmio = defaultdict(int)
for i in range(0, N - 4, 4):
    v = struct.unpack_from('<I', av, i)[0]
    if 0xF0000000 <= v <= 0xFFFFFFFF and (v & 0xFFF) == 0:
        mmio[v] += 1
    elif 0xC0000000 <= v <= 0xEFFFFFFF and (v & 0xFFFF) == 0:
        mmio[v] += 1
print('  %d distinct page-aligned peripheral-looking constants' % len(mmio))
for k in sorted(mmio, key=lambda x: -mmio[x])[:30]:
    print('    0x%08x  x%d' % (k, mmio[k]))
