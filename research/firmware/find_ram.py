"""Find firmware-declared RAM addresses we could poke as an observable.

A 4-byte store to a buffer the firmware's own config names is a far safer
demonstration than a framebuffer write: single aligned word, into a region
the firmware already uses as a log buffer, and readable afterwards with xxd.

Searching the extracted trees and the ulogio record file for address-bearing
config strings.
"""
import re
from pathlib import Path

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')

# 1. the ulogio.bin record file: [u32 tag][u32 value] pairs
p = Path(r'C:\Users\qn061\AppData\Local\Temp\opencode\ulogio.orig.bin')
if p.exists():
    import struct
    b = p.read_bytes()
    print('=== /setting/ulogio.bin  [%u32 tag][u32 value] ===' % 0)
    print('  %d bytes, %d records' % (len(b), len(b) // 8))
    for i in range(0, len(b) - 7, 8):
        tag, val = struct.unpack_from('<II', b, i)
        t = tag.to_bytes(4, 'big')
        try:
            name = t.decode('ascii')
        except UnicodeDecodeError:
            name = ''
        if not name.isprintable():
            continue
        if 0x00100000 <= val <= 0x08000000:
            kind = 'RAM address' if val < 0x04000000 else 'peripheral/MMIO'
            print('  0x%04x  %-6s = 0x%08x  %10d  <- %s' % (i, name, val, val, kind))
        elif val and val < 0x100000:
            print('  0x%04x  %-6s = %d' % (i, name, val))
    print()

# 2. any config text in the dumps that names addresses
print('=== address-bearing config strings in the dumps ===')
pat = re.compile(rb'[\x20-\x7e]{4,200}')
hits = {}
roots = [BASE / 'dumps' / 'camera_2025' / 'etc',
         BASE / 'dumps' / 'camera_2025' / 'usr_bin',
         BASE / 'dumps']
seen = set()
for root in roots:
    if not root.is_dir():
        continue
    for f in list(root.rglob('*'))[:4000]:
        if not f.is_file():
            continue
        try:
            if f.stat().st_size > 4_000_000:
                continue
            b = f.read_bytes()
        except OSError:
            continue
        for m in pat.finditer(b):
            s = m.group().decode('latin1')
            if re.search(r'0x[0-9a-fA-F]{6,8}', s) and re.search(
                    r'(addr|\.addr|base|buf|buffer|log|heap|pool|frame)', s, re.I):
                key = s.strip()[:120]
                if key in seen:
                    continue
                seen.add(key)
                hits.setdefault(key, str(f.relative_to(BASE)))
for k in sorted(hits)[:40]:
    print('  %-96s  <- %s' % (k, hits[k]))
print('  (%d unique)' % len(hits))
print()

print('=== what a safe poke looks like ===')
print('  movw/movt the address, then str - 6 bytes of code, no call at all.')
print('  Example shape:')
print('     ldr  r2, [pc, #K]      ; or movw/movt for a 32-bit address')
print('     str  r3, [r2]          ; one aligned 32-bit store')
print('  No ABI assumptions, no wild pointer beyond the single store, and')
print('  observable afterwards with:  busybox xxd -s <off> -l 16 <file>')
