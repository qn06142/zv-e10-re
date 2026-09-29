"""Resolve the VDF Execute/Activate log strings to real functions.

These are LOG strings (they contain the full C++ signature), so unlike RTTI
type names they ARE referenced PC-relative and resolve to genuine code.  That
gives the real Execute/Activate methods by name instead of guessing which
vtable slot is which.

Then pick the hook: SetPanelReverse is the most visible reversible change.
"""
import re
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from thumb import mkdis, dis1, is_return, is_prologue, walk, calls_of       # noqa: E402
from capstone.arm import ARM_OP_REG, ARM_OP_MEM                              # noqa: E402

BASE = 0x635C6000
av = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
N = len(av)
md = mkdis()

logstr = {}
for m in re.finditer(rb'virtual VDF::VDF_ERR VDF::[A-Za-z]+::(Execute|Activate)\(', av):
    s = m.group().decode('latin1')
    logstr[m.start()] = s
print('=== %d Execute/Activate log strings ===' % len(logstr))
print()

branch_targets = set()
for i in range(0, N - 4, 2):
    hw1, hw2 = struct.unpack_from('<HH', av, i)
    if hw1 & 0xF800 != 0xF000:
        continue
    s = (hw1 >> 10) & 1
    imm10 = hw1 & 0x3FF
    j1, j2 = (hw2 >> 13) & 1, (hw2 >> 11) & 1
    imm11 = hw2 & 0x7FF
    i1, i2 = (~(j1 ^ s)) & 1, (~(j2 ^ s)) & 1
    v = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
    if v & 0x1000000:
        v -= 0x2000000
    branch_targets.add(i + 4 + v)

seeds = [t for t in sorted(branch_targets)
         if 0x1000 <= t < 0xAED000 and is_prologue(av, t)]
users = defaultdict(list)
covered = set()
for seed in seeds:
    if seed in covered:
        continue
    pending = {}
    addr = seed
    limit = min(seed + 0x2000, 0xAED000, N)
    while addr < limit:
        if addr in covered:
            break
        covered.add(addr)
        ins = dis1(md, av[addr:addr + 4], addr)
        if ins is None:
            break
        ops = ins.operands
        if ins.mnemonic.split('.')[0] == 'ldr' and len(ops) == 2 \
                and ops[1].type == ARM_OP_MEM and ops[1].mem.base == 11 \
                and ops[0].type == ARM_OP_REG:
            la = ((addr + 4) & ~3) + ops[1].mem.disp
            if 0 <= la <= N - 4:
                pending[ops[0].reg] = struct.unpack_from('<I', av, la)[0]
        if ins.mnemonic.split('.')[0] in ('add', 'addw', 'adr') and len(ops) >= 2 \
                and ops[1].type == ARM_OP_REG and ops[0].type == ARM_OP_REG \
                and ops[0].reg in pending:
            tgt = pending.pop(ops[0].reg) + (addr + 4)
            if 0 < tgt < N:
                users[tgt].append((seed, addr))
        if is_return(ins):
            break
        addr += ins.size
print('  swept %d addresses, %d targets' % (len(covered), len(users)))
print()

print('=== Execute/Activate resolved to code ===')
resolved = {}
for off, s in sorted(logstr.items()):
    hits = users.get(off, [])
    if not hits:
        continue
    fn, pc = hits[0]
    # the string is "virtual VDF::VDF_ERR VDF::ClassName::Method(args)".
    # Splitting on 'VDF::' and taking [1] grabbed the RETURN TYPE ("VDF_ERR"),
    # not the class - take the LAST field before the '(' instead.
    name = s.split('(')[0].strip().split()[-1]
    body = walk(md, av, fn, 0x800)
    cl = calls_of(body)
    print('  %-52s fn 0x%08x  ref@0x%08x  %d insn, %d call(s)'
          % (name[:52], fn, pc, len(body), len(cl)))
    resolved[name] = (fn, cl)

print()
print('=== SetPanelReverse detail ===')
for key in ('VdfDisplayCmdSetPanelReverse::Activate',
            'VdfDisplayCmdSetPanelReverse::Execute'):
    if key in resolved:
        fn, cl = resolved[key]
        print('\n%s at 0x%08x' % (key, fn))
        for i in walk(md, av, fn, 0x180):
            print('  0x%08x  %-12s %-36s' % (i.address, i.bytes.hex(' '),
                                            i.mnemonic + ' ' + i.op_str))
print()
print('=== which MMIO-looking constants appear in these functions? ===')
seen = set()
for key, (fn, cl) in resolved.items():
    for ins in walk(md, av, fn, 0x800):
        if ins.mnemonic.split('.')[0] in ('movw', 'movt') or ins.mnemonic.startswith('ldr.w'):
            o = ins.op_str
            if '#0x' in o:
                v = int(o.split('#0x')[1].split(']')[0].rstrip('x'), 16) if ']' not in o else None
                if v and v >= 0x1000 and (key, v) not in seen:
                    seen.add((key, v))
                    if 0xF0000000 <= v <= 0xFFFFFFFF or 0xC0000000 <= v <= 0xEFFFFFFF:
                        print('  %-40s 0x%08x  <- peripheral' % (key[:40], v))
