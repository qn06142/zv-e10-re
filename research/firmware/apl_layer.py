"""The decoder does not memcpy its planes (only 2 sites in 0xa0000..0xba000).
The picture goes out via APL DMA: apl_mov_set_dma_addr / apl_mov_start.

Locate the APL layer: which functions reference those symbols, and what does
the DMA-setup code look like?
"""
import re
import struct
from collections import defaultdict
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN
from capstone.arm import ARM_OP_REG, ARM_OP_MEM

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
av = (BASE / 'dumps' / 'av-cam.bin.bak').read_bytes()
N = len(av)
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
md.detail = True

MEMCPY = 0x52E120
DEC_LO, DEC_HI = 0xA0000, 0xBA000


def dis1(buf, addr):
    for extra in (b'', b'\x00' * 4, b'\x00' * 8, b'\x00' * 16):
        for i in md.disasm(bytes(buf) + extra, addr):
            return i
    return None


def is_return(i):
    b = i.mnemonic.split('.')[0]
    if b == 'bx':
        return True
    return b in ('pop', 'ldm', 'ldmia', 'ldmdb', 'ldmia') and 'pc' in i.op_str


# ---- the 2 decoder memcpy sites, in context -------------------------------
print('=== the only 2 memcpy call sites inside the decoder range ===')
for i in range(DEC_LO, DEC_HI, 2):
    hw1, hw2 = struct.unpack_from('<HH', av, i)
    if hw1 & 0xF800 != 0xF000 or (hw1 & 0xF000) != 0xF000 or (hw1 & 0x0800):
        continue
    s = (hw1 >> 10) & 1
    imm10 = hw1 & 0x3FF
    j1, j2 = (hw2 >> 13) & 1, (hw2 >> 11) & 1
    imm11 = hw2 & 0x7FF
    i1, i2 = (~(j1 ^ s)) & 1, (~(j2 ^ s)) & 1
    v = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
    if v & 0x1000000:
        v -= 0x2000000
    if i + 4 + v != MEMCPY:
        continue
    print()
    print('  --- call site 0x%08x ---' % i)
    addr = i - 0x30
    n = 0
    while addr <= i + 0x10 and n < 40:
        ins = dis1(av[addr:addr + 4], addr)
        if ins is None:
            break
        flag = '   <<<< memcpy' if addr == i else ''
        if ins.mnemonic == 'bl':
            try:
                t = int(ins.op_str.split('#')[-1], 16)
                if t not in (MEMCPY,) and 0x52E000 <= t <= 0x530000:
                    flag += '   (neighbouring 0x52Exxx)'
            except ValueError:
                pass
        print('    0x%08x  %-12s %-34s%s' % (addr, ins.bytes.hex(' '),
                                              ins.mnemonic + ' ' + ins.op_str, flag))
        addr += ins.size
        n += 1
print()

# ---- APL strings in the image ---------------------------------------------
print('=== apl_* symbols and messages in av-cam.bin ===')
apl = defaultdict(list)
for m in re.finditer(rb'[\x20-\x7e]{6,120}', av):
    s = m.group().decode('latin1')
    if re.search(r'APL|apl_mov|apl_lmv|apl_set|apl_start|dma|DMA', s):
        apl[s].append(m.start())
for s in sorted(apl):
    if len(apl[s]) <= 4:
        print('  %-88s %s' % (s[:88], ' '.join('0x%07x' % o for o in apl[s][:3])))
print('  (%d distinct strings total)' % len(apl))
print()

# ---- which functions call into the 0x6b4xxx / 0x6bdxxx APL-ish band? -----
print('=== call density: which address bands does the decoder call into? ===')
band = defaultdict(int)
for i in range(0, N - 4, 2):
    hw1, hw2 = struct.unpack_from('<HH', av, i)
    if hw1 & 0xF800 != 0xF000 or (hw1 & 0xF000) != 0xF000 or (hw1 & 0x0800):
        continue
    if not (DEC_LO <= i < DEC_HI):
        continue
    s = (hw1 >> 10) & 1
    imm10 = hw1 & 0x3FF
    j1, j2 = (hw2 >> 13) & 1, (hw2 >> 11) & 1
    imm11 = hw2 & 0x7FF
    i1, i2 = (~(j1 ^ s)) & 1, (~(j2 ^ s)) & 1
    v = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
    if v & 0x1000000:
        v -= 0x2000000
    band[(i + 4 + v) >> 12] += 1
for k in sorted(band, key=lambda x: -band[x])[:16]:
    print('  0x%05x000  %6d calls' % (k, band[k]))
