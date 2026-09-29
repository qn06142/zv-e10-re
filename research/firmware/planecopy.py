"""Confirm 0x52E120 is memcpy, then read the two plane-copy functions to find
which argument is the destination pointer.
"""
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN
from capstone.arm import ARM_OP_REG, ARM_OP_IMM, ARM_OP_MEM

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
av = (BASE / 'dumps' / 'av-cam.bin.bak').read_bytes()
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
md.detail = True


def dis1(buf, addr):
    for extra in (b'', b'\x00' * 4, b'\x00' * 8, b'\x00' * 16):
        for i in md.disasm(bytes(buf) + extra, addr):
            return i
    return None


def show(start, count, title):
    print('=== %s  (0x%08x) ===' % (title, start))
    addr = start
    n = 0
    while n < count:
        i = dis1(av[addr:addr + 4], addr)
        if i is None:
            break
        flag = ''
        o = i.op_str
        if i.mnemonic == 'bl':
            try:
                t = int(o.split('#')[-1], 16)
                if t == 0x52E120:
                    flag = '   <<<< memcpy?'
            except ValueError:
                pass
        if i.mnemonic.startswith('str'):
            flag += '   <-- write'
        print('  0x%08x  %-12s %-34s%s' % (addr, i.bytes.hex(' '),
                                            i.mnemonic + ' ' + o, flag))
        addr += i.size
        n += 1
        if i.mnemonic in ('pop', 'bx') and 'pc' in o:
            break
    print()


show(0x52E120, 22, 'the callee at 0x52E120')
show(0x6B438E, 60, 'plane copy #1')
show(0x6B43C2, 60, 'plane copy #2')

print('=== is 0x52E120 referenced from a lot of places? (memcpy is generic) ===')
cnt = 0
for i in range(0, len(av) - 4, 2):
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
    if i + 4 + v == 0x52E120:
        cnt += 1
print('  direct BL call sites to 0x52E120: %d' % cnt)
print('  (a low hundreds/thousands => a generic library routine like memcpy)')
