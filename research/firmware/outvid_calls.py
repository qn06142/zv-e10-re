"""Call graph around the decoder output-video module, anchored on the
ring-buffer function (per-frame by name).

Also: fully interpret 0xB7688's hardcoded +0x90530 buffer access.
"""
import struct
from collections import defaultdict
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
av = (BASE / 'dumps' / 'av-cam.bin.bak').read_bytes()
N = len(av)
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)

OUTVID = [0x000b6e78, 0x000b6f68, 0x000b7128, 0x000b71aa, 0x000b7230,
          0x000b7358, 0x000b73c0, 0x000b7688, 0x000b78ec, 0x000b79b4,
          0x000b818c, 0x000b82b8]
RING = 0x000b98bc            # references sfmc_dec_ring_buffer_with_pts.cpp


def dis1(buf, addr):
    for extra in (b'', b'\x00' * 4, b'\x00' * 8, b'\x00' * 16):
        for i in md.disasm(bytes(buf) + extra, addr):
            return i
    return None


# ---- who calls whom -------------------------------------------------------
callers = defaultdict(set)
for i in range(0, N - 4, 2):
    hw1, hw2 = struct.unpack_from('<HH', av, i)
    if hw1 & 0xF800 != 0xF000 or (hw1 & 0xF000) != 0xF000:
        continue
    if hw1 & 0x0800:                       # B.W, not BL
        continue
    s = (hw1 >> 10) & 1
    imm10 = hw1 & 0x3FF
    j1, j2 = (hw2 >> 13) & 1, (hw2 >> 11) & 1
    imm11 = hw2 & 0x7FF
    i1, i2 = (~(j1 ^ s)) & 1, (~(j2 ^ s)) & 1
    v = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
    if v & 0x1000000:
        v -= 0x2000000
    callers[i + 4 + v].add(i)

print('=== direct callers of each output_video function ===')
allf = OUTVID + [RING]
for f in allf:
    c = sorted(callers.get(f, ()))
    tag = '  <- ring_buffer_with_pts' if f == RING else ''
    print('  0x%08x : %d caller(s)  %s%s' % (
        f, len(c), ' '.join('0x%06x' % x for x in c[:8]), tag))
print()

print('=== who calls the ring-buffer function? (the per-frame anchor) ===')
for c in sorted(callers.get(RING, ())):
    # which module does the calling function belong to?
    print('  caller 0x%06x' % c)
print()

print('=== 0xB7688 in full: interpret the +0x90530 access ===')
addr = 0xB7688
n = 0
while addr < 0xB7688 + 0x260 and n < 130:
    ins = dis1(av[addr:addr + 4], addr)
    if ins is None:
        break
    flag = ''
    o = ins.op_str
    if '0x90530' in o or '0x90000' in o:
        flag = '   <<< buffer offset'
    if ins.mnemonic in ('bl', 'b.w', 'b') and '#' in o:
        try:
            t = int(o.split('#')[-1], 16)
            if t in allf or t == RING:
                flag += '   <<< calls 0x%06x' % t
        except ValueError:
            pass
    print('  0x%08x  %-12s %-34s%s' % (addr, ins.bytes.hex(' '),
                                        ins.mnemonic + ' ' + o, flag))
    addr += ins.size
    n += 1
    if ins.mnemonic in ('pop', 'bx') and 'pc' in o:
        break
