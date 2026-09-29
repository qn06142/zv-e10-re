"""The 0x6B40xx layer: find the function that actually writes picture data.

0xB73C0 turned out to be a validate-and-log wrapper over a ~300-byte-header
descriptor, so the real work is one level down.  This cluster is called from
four different sfmc_dec_output_video functions, which is what a shared
output/format/copy layer looks like.

Also identify which source file this region belongs to, by resolving the
PC-relative references made from it.
"""
import struct
from collections import defaultdict
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN
from capstone.arm import ARM_OP_REG, ARM_OP_IMM, ARM_OP_MEM

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
av = (BASE / 'dumps' / 'av-cam.bin.bak').read_bytes()
N = len(av)
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
md.detail = True

LO, HI = 0x6B3E00, 0x6B4400


def dis1(buf, addr):
    for extra in (b'', b'\x00' * 4, b'\x00' * 8, b'\x00' * 16):
        for i in md.disasm(bytes(buf) + extra, addr):
            return i
    return None


def decode_movw(hw1, hw2):
    if (hw1 >> 11) != 0b11110 or (hw2 >> 15):
        return None, None
    if ((hw1 >> 4) & 0x3F) not in (0b100100, 0b101000):
        return None, None
    return (((hw1 & 0xF) << 12) | (((hw1 >> 10) & 1) << 11)
            | (((hw2 >> 12) & 7) << 8) | (hw2 & 0xFF)), (hw2 >> 8) & 0xF


def walk(start, limit=0x1200):
    out = []
    addr = start
    while addr < start + limit and addr < HI + 0x2000:
        i = dis1(av[addr:addr + 4], addr)
        if i is None:
            break
        out.append(i)
        addr += i.size
        if i.mnemonic in ('pop', 'bx') and 'pc' in i.op_str:
            break
    return out


# ---- enumerate function starts in the region -----------------------------
print('=== function starts in 0x%06x..0x%06x ===' % (LO, HI))
starts = []
addr = LO
while addr < HI:
    hw = struct.unpack_from('<H', av, addr)[0]
    if (hw & 0xFF00) == 0xB500 and (hw & 0x80):
        starts.append(addr)
        addr += 2
    else:
        hw1 = struct.unpack_from('<H', av, addr)[0]
        if hw1 == 0xE92D or (hw1 & 0xFF00) == 0xE800:
            starts.append(addr)
            addr += 2
        else:
            addr += 2
print('  %d prologue(s): %s' % (len(starts), ' '.join('0x%06x' % s for s in starts)))
print()

for f in starts:
    insns = walk(f, 0x800)
    if not insns:
        continue
    end = insns[-1].address + insns[-1].size
    calls = []
    for i in insns:
        if i.mnemonic == 'bl':
            try:
                calls.append(int(i.op_str.split('#')[-1], 16))
            except ValueError:
                pass
    stores = [i for i in insns if i.mnemonic.startswith('str')]
    idx_st = [i for i in stores
              if any(o.type == ARM_OP_MEM and o.mem.index for o in i.operands)]
    imms = []
    for k in range(len(insns)):
        pass
    # movw immediates
    a = f
    for i in insns:
        b = av[i.address:i.address + 4]
        if len(b) == 4:
            v, _ = decode_movw(*struct.unpack_from('<HH', b, 0))
            if v is not None and v >= 0x40:
                imms.append(v)
    # backward branches = loops
    loops = [i for i in insns if i.mnemonic in ('b', 'bne', 'beq', 'blt', 'bgt', 'bge', 'ble', 'bhi', 'bls', 'bcc', 'bcs')
             and '#-' in i.op_str]
    print('0x%06x .. 0x%06x  %4d insns  calls=%-3d stores=%-3d idxstores=%-3d backbranches=%d' % (
        f, end, len(insns), len(calls), len(stores), len(idx_st), len(loops)))
    print('   movw imms: %s' % ' '.join('0x%x' % v for v in imms[:14]))
    print('   calls: %s' % ' '.join('0x%06x' % c for c in calls[:14]))
print()

# ---- which source file does this region belong to? ------------------------
print('=== source strings referenced from this region ===')
pending = {}
refs = []
addr = LO
while addr < HI + 0x2000:
    i = dis1(av[addr:addr + 4], addr)
    if i is None:
        addr += 2
        continue
    ops = i.operands
    if i.mnemonic.startswith('ldr') and len(ops) == 2 and ops[1].type == ARM_OP_MEM \
            and ops[1].mem.base == 11:
        la = ((addr + 4) & ~3) + ops[1].mem.disp
        if 0 <= la <= N - 4:
            pending[ops[0].reg] = struct.unpack_from('<I', av, la)[0]
    if i.mnemonic in ('add', 'addw', 'adr') and len(ops) >= 2 and ops[1].type == ARM_OP_REG \
            and ops[0].type == ARM_OP_REG and ops[0].reg in pending:
        tgt = pending.pop(ops[0].reg) + (addr + 4)
        if 0 < tgt < N:
            end = av.find(b'\x00', tgt, tgt + 90)
            if end > tgt:
                s = av[tgt:end]
                if all(32 <= c < 127 for c in s) and len(s) > 3:
                    refs.append((addr, s.decode('ascii')))
    addr += i.size

seen = set()
for at, s in refs:
    if s in seen:
        continue
    seen.add(s)
    print('  0x%06x  %s' % (at, s[:88]))
print('  (%d unique)' % len(seen))
