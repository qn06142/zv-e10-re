"""Sound reachability for code caves in av-cam.bin.

The previous scan was unsound: Sony stores cross-references PC-relative
(ldr rX,[pc,#imm] ; add rX,pc), so raw-address and raw-pointer searches
miss them.  That produced 88% "unreachable", which is not credible.

Sound approach:
  * seeds = function entries that ARE direct branch targets (7,074 of them,
    verified by the branch scan - these are definitely real entries)
  * from each seed, linear-disassemble forward, tracking ldr rX,[pc,#imm]
    and resolving a following `add rX, pc` into a real target address
  * every resolved address is a genuine cross-reference
  * a candidate cave is safe only if it is neither branch-referenced nor
    resolved as a PC-relative reference, from any seed
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

MAX_FN = 0x3000
CODE_LO, CODE_HI = 0x1000, 0xAED000

# ---------------------------------------------------------------- 1. seeds
branch_targets = set()
for i in range(0, N - 4, 2):
    hw1, hw2 = struct.unpack_from('<HH', av, i)
    if hw1 & 0xF800 != 0xF000:
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
    if hw1 & 0x0800:
        branch_targets.add(i + 4 + v)                       # B.W
    else:
        v16 = hw1 & 0x7FF
        if v16 & 0x400:
            v16 -= 0x800
        branch_targets.add(i + 4 + (v16 << 1))             # 16-bit B

# seeds must look like a prologue
seeds = []
for t in sorted(branch_targets):
    if not (CODE_LO <= t < CODE_HI) or t + 2 > N:
        continue
    hw = struct.unpack_from('<H', av, t)[0]
    hw2 = struct.unpack_from('<H', av, t + 2)[0] if t + 4 <= N else 0
    if (hw & 0xFF00) == 0xB500 and (hw & 0x80):
        seeds.append(t)
    elif hw == 0xE92D or (hw & 0xFF00) == 0xB500:
        seeds.append(t)
    elif (hw & 0xFE00) == 0xB400 or (hw & 0xFF00) == 0xB500:
        seeds.append(t)
seeds = sorted(set(seeds))
print('=== seeds: branch-referenced prologues ===')
print('  %d seeds between 0x%x and 0x%x' % (len(seeds), CODE_LO, CODE_HI))
print()

# ------------------------------------------- 2. PC-relative reference sweep
referenced = set(branch_targets)
resolved_str = set()
n_ins = 0
n_fn = 0

for seed in seeds:
    n_fn += 1
    pending = {}                     # reg -> literal value loaded from a pool
    addr = seed
    limit = min(seed + MAX_FN, CODE_HI, N)
    while addr < limit:
        chunk = av[addr:addr + 4]
        if len(chunk) < 2:
            break
        ins = None
        for cand in md.disasm(chunk, addr, count=1):
            ins = cand
            break
        if ins is None:
            break
        n_ins += 1
        ops = ins.operands
        m = ins.mnemonic
        if m in ('b', 'b.w') and ops and ops[0].type == ARM_OP_IMM:
            tgt = ops[0].imm
            referenced.add(tgt)
            if not (m == 'b.w' and False):
                break                # unconditional: stop at end of block
        if m in ('pop', 'pop.w', 'bx') and 'pc' in ins.op_str:
            break
        if m in ('bx', 'blx') and ops and ops[0].type == ARM_OP_REG:
            break
        if m in ('ldrb', 'ldrh', 'ldr') and len(ops) == 2 and ops[1].type == ARM_OP_MEM:
            mem = ops[1].mem
            if mem.base == 13:       # ARM_REG_PC == 13
                lit_addr = ((addr + 4) & ~3) + mem.disp
                if 0 <= lit_addr <= N - 4:
                    val = struct.unpack_from('<I', av, lit_addr)[0]
                    if ops[0].type == ARM_OP_REG:
                        pending[ops[0].reg] = val
                    # also: a pool word that is itself a code address
                    if CODE_LO < val < CODE_HI:
                        referenced.add(val)
        if m in ('add', 'add.w', 'adr') and len(ops) >= 2 and ops[1].type == ARM_OP_REG:
            if ops[0].type == ARM_OP_REG and ops[0].reg in pending:
                tgt = pending.pop(ops[0].reg) + (addr + 4)
                if 0 < tgt < N:
                    referenced.add(tgt)
                    if CODE_LO < tgt < CODE_HI:
                        referenced.add(tgt)
        addr += ins.size
    if n_fn % 2000 == 0:
        print('  ...%d functions, %d insns, %d referenced' % (n_fn, n_ins, len(referenced)))

print()
print('=== sweep complete ===')
print('  functions swept : %d' % n_fn)
print('  instructions    : %d' % n_ins)
print('  referenced addrs: %d' % len(referenced))
print()

# --------------------------------------------------------- 3. cave scoring
entries = []
for i in range(CODE_LO, CODE_HI - 2, 2):
    hw = struct.unpack_from('<H', av, i)[0]
    if (hw & 0xFF00) == 0xB500 and (hw & 0x80):
        entries.append(i)
unreach = [e for e in entries if e not in referenced]
print('=== %d candidate prologues, %d unreferenced (%.1f%%) ===' % (
    len(entries), len(unreach), 100.0 * len(unreach) / max(1, len(entries))))
print()

runs = []
if unreach:
    s = p = unreach[0]
    for e in unreach[1:]:
        if e - p <= 0x200:
            p = e
        else:
            runs.append((s, p))
            s = p = e
    runs.append((s, p))
print('=== largest unreferenced clusters ===')
for s, e in sorted(runs, key=lambda t: -(t[1] - t[0]))[:10]:
    print('  0x%08x .. 0x%08x   span %7d bytes' % (s, e, e - s))
print()
print('NOTE: "unreferenced" now means no inbound branch and no PC-relative')
print('reference resolved from any of the %d branch-verified seeds.' % len(seeds))
print('It is still not proof of deadness - only that nothing in the swept')
print('code refers to it. A live-but-unreferenced entry is possible if its')
print('only caller sits in a region the seeds did not cover.')
