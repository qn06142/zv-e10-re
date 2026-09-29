"""Resolve the PC-relative string pointers in the error path of the patched
function, and identify what 0xa9f90 / 0x6aa366 are.

If the strings name a playback source file, that is the whole answer to
"why did only video playback break".
"""
import re
import struct
from pathlib import Path

N = 17_289_388
a = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
FUNC = 0x000aa14c          # push {r4,lr} - start of the patched function


def cstr(off, n=120):
    if off is None or off < 0 or off >= N:
        return None
    end = a.find(b'\x00', off, off + n)
    if end < 0:
        return None
    s = a[off:end]
    if len(s) < 2:
        return None
    try:
        t = s.decode('ascii')
    except UnicodeDecodeError:
        return None
    return t if all(32 <= ord(c) < 127 for c in t) else None


print('=== error-path literals, resolved by hand from the disassembly ===')
# ldr r3,[pc,#0x24] @0xaa172 ; add r3,pc @0xaa178
lit1_addr = ((0xaa172 + 4) & ~3) + 0x24
off1 = struct.unpack_from('<i', a, lit1_addr)[0]
str1 = ((0xaa178 + 4) & ~3) + off1
# ldr r3,[pc,#0x18] @0xaa182 ; add r3,pc @0xaa184
lit2_addr = ((0xaa182 + 4) & ~3) + 0x18
off2 = struct.unpack_from('<i', a, lit2_addr)[0]
str2 = ((0xaa184 + 4) & ~3) + off2
print('  literal pool @0x%06x = 0x%08x  -> string @0x%08x' % (lit1_addr, off1, str1))
print('  literal pool @0x%06x = 0x%08x  -> string @0x%08x' % (lit2_addr, off2, str2))
print('    #1 = %r' % cstr(str1))
print('    #2 = %r' % cstr(str2))
print()

print('=== every string within 0x400 of the patched function ===')
lo, hi = FUNC - 0x400, FUNC + 0x400
for m in re.finditer(rb'[\x20-\x7e]{4,}', a[lo:hi]):
    o = lo + m.start()
    print('  0x%06x (+%+#07x)  %s' % (o, o - FUNC, m.group().decode('ascii')[:100]))
print()

print('=== the removed callee at 0xa9f90: first instructions ===')
for i in range(0xa9f90, 0xa9f90 + 0x40, 2):
    print('  0x%06x  %s %s' % (i, a[i:i + 2].hex(' '), ''), end='')
    print()
print()
print('  raw 0xa9f90..0xa9fd0: %s' % a[0xa9f90:0xa9fd0].hex(' '))
print()

print('=== nearby function starts (push {... lr} / bx lr) around the callee ===')
for i in range(0xa9e00, 0xaa000, 2):
    w = a[i:i + 2]
    if w in (b'\xb5\x10', b'\xb5\xf0', b'\x2d\xe9', b'\xf0\xb5', b'\x70\xb5'):
        print('  0x%06x  %s' % (i, w.hex(' ')))
print()

print('=== does anything else in the image call 0xaa14c? (the patched fn) ===')
# scan for BL encodings whose target is FUNC
hits = 0
for i in range(0, N - 4, 2):
    hw1, hw2 = struct.unpack_from('<HH', a, i)
    if hw1 & 0xF800 != 0xF000:
        continue
    if hw1 & 0x0800:          # B (T2) - skip, only care about BL
        continue
    s = (hw1 >> 10) & 1
    imm10 = hw1 & 0x3FF
    j1 = (hw2 >> 13) & 1
    j2 = (hw2 >> 11) & 1
    imm11 = hw2 & 0x7FF
    i1 = (~(j1 ^ s)) & 1
    i2 = (~(j2 ^ s)) & 1
    v = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
    if v & 0x1000000:
        v -= 0x2000000
    if i + 4 + v == FUNC:
        print('  caller at 0x%06x' % i)
        hits += 1
print('  total direct BL callers: %d' % hits)
