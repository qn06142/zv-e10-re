"""Which of the 12 sfmc_dec_output_video functions touches the pixel buffer?

A per-frame video-output function will show one of:
  * a pointer parameter used as a base with a stride-sized displacement
  * large immediate offsets (struct fields, buffer strides)
  * a loop that walks memory (lsl/add on a pointer, or a byte/word store
    with a computed index)
"""
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN
from capstone.arm import ARM_OP_REG, ARM_OP_IMM, ARM_OP_MEM

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
av = (BASE / 'dumps' / 'av-cam.bin.bak').read_bytes()
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
md.detail = True

FUNCS = [0x000b6e78, 0x000b6f68, 0x000b7128, 0x000b71aa, 0x000b7230,
         0x000b7358, 0x000b73c0, 0x000b7688, 0x000b78ec, 0x000b79b4,
         0x000b818c, 0x000b82b8]


def dis1(buf, addr):
    for extra in (b'', b'\x00' * 4, b'\x00' * 8, b'\x00' * 16):
        for i in md.disasm(bytes(buf) + extra, addr):
            return i
    return None


def walk(start, maxlen=0x600):
    insns = []
    addr = start
    while addr < start + maxlen and addr < len(av):
        i = dis1(av[addr:addr + 4], addr)
        if i is None:
            break
        insns.append(i)
        addr += i.size
        if i.mnemonic in ('pop', 'bx') and 'pc' in i.op_str:
            break
    return insns


print('=== the 12 sfmc_dec_output_video functions ===')
for f in FUNCS:
    insns = walk(f)
    if not insns:
        print('\n0x%08x  <no disassembly>' % f)
        continue
    end = insns[-1].address + insns[-1].size
    # prologue: what does it take as parameters?
    pro = ' | '.join('%s %s' % (i.mnemonic, i.op_str) for i in insns[:4])
    # big displacements = struct fields / buffer strides
    big = []
    for i in insns:
        for op in i.operands:
            if op.type == ARM_OP_MEM and abs(op.mem.disp) >= 0x40:
                big.append('0x%x %s[%s,#%#x]' % (
                    i.address, i.mnemonic, i.reg_name(op.mem.base), op.mem.disp))
    # stores with a register index = element-wise pixel writes
    pix = [i for i in insns
           if i.mnemonic.startswith('str') and any(
               op.type == ARM_OP_MEM and op.mem.index != 0 for op in i.operands)]
    # shifts = stride arithmetic
    sh = [i for i in insns if i.mnemonic in ('lsl', 'lsls', 'lsl.w', 'add', 'addw')
          and '#' in i.op_str and any(
              op.type == ARM_OP_IMM and op.imm >= 0x40 for op in i.operands)]
    print('\n0x%08x .. 0x%08x  (%d insns, %d bytes)' % (f, end, len(insns), end - f))
    print('   prologue : %s' % pro[:110])
    print('   big mem  : %s' % (', '.join(big[:8]) or 'none'))
    print('   indexed st: %d   stride-ish arith: %d' % (len(pix), len(sh)))
    if pix:
        print('      e.g. %s' % '; '.join(
            '%s %s' % (p.mnemonic, p.op_str) for p in pix[:3]))
    if sh:
        print('      e.g. %s' % '; '.join(
            '%s %s' % (s.mnemonic, s.op_str) for s in sh[:3]))
    calls = [i for i in insns if i.mnemonic in ('bl', 'blx')]
    tgts = []
    for c in calls:
        try:
            tgts.append(c.op_str.split('#')[-1])
        except Exception:
            pass
    print('   calls    : %d  %s' % (len(tgts), ' '.join(tgts[:10])))
