"""Disassemble 0xB73C0 to choose the hook slot.

Requirements for the slot:
  * exactly 4 bytes, so a B.W replaces it with no size change
  * after `mov sb, r2` (so r9/sb already holds the buffer pointer)
  * ideally a BL, so the cave can re-issue it and branch back
"""
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN
from capstone.arm import ARM_OP_REG

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
av = (BASE / 'dumps' / 'av-cam.bin.bak').read_bytes()
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
md.detail = True

FUNC = 0x000B73C0


def dis1(buf, addr):
    for extra in (b'', b'\x00' * 4, b'\x00' * 8, b'\x00' * 16):
        for i in md.disasm(bytes(buf) + extra, addr):
            return i
    return None


print('=== 0x%08x, first 0x90 bytes ===' % FUNC)
addr = FUNC
n = 0
while addr < FUNC + 0x90 and n < 70:
    i = dis1(av[addr:addr + 4], addr)
    if i is None:
        break
    uses_r9 = any(o.type == ARM_OP_REG and i.reg_name(o.reg) in ('r9', 'sb')
                  for o in i.operands)
    flag = ''
    if i.mnemonic == 'bl':
        flag = '   <== 4-byte BL, candidate hook slot'
    if i.op_str.startswith(('sb,', 'r9,')):
        flag = '   <== buffer saved to sb/r9'
    print('  0x%08x  %-12s %-36s%s' % (addr, i.bytes.hex(' '),
                                        i.mnemonic + ' ' + i.op_str, flag))
    addr += i.size
    n += 1

print()
print('=== candidate summary ===')
# re-scan for 4-byte BLs in the first 0x80 bytes
addr = FUNC
cands = []
while addr < FUNC + 0x80:
    i = dis1(av[addr:addr + 4], addr)
    if i is None:
        break
    if i.mnemonic == 'bl' and i.size == 4:
        try:
            cands.append((addr, int(i.op_str.split('#')[-1], 16)))
        except ValueError:
            pass
    addr += i.size
for a, t in cands:
    print('  slot 0x%08x  ->  bl 0x%08x' % (a, t))
print()
print('  a B.W at the slot, then in the cave: scribble, `bl 0x%08x`, b.w back.' % (
    cands[0][1] if cands else 0))
