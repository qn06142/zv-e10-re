"""Locate the APL layer in av-cam.bin, to get the display/MMIO bases.

/proc/cmdline already told us the DDR carve-outs:
    wbimem=0x500000@0x03085000     5 MB    <- checked: 79% zeros, a log ring
    wbimem=0x96D000@0x11000000     9.4 MB  <- NOT yet examined
    wbimem=0x2A48000@0x20200000   44.4 MB  <- NOT yet examined
    wbimem=0x200000@0x23E00000     2 MB
    wbi_cmpr.waddr=0x6AA00000 wbi_cmpr.wsize=0x100000 wbi_cmpr.nbuf=12
                                 12 x 1 MB ring  <- NOT yet examined

and the APL strings name registers, including an eSRAM variant that would be
on-chip SRAM and therefore NOT in iomem as System RAM:
    apl_mov_set_aic R0/R1/R2, W0/W1/W2, each with (DDR) and (eSRAM) variants

So: find the functions that emit those errors, and read the base addresses
they build with movw/movt.  That gives exact MMIO + buffer addresses.
"""
import re
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from thumb import mkdis, dis1, is_return, is_prologue, walk, decode_movw  # noqa: E402
from capstone.arm import ARM_OP_REG, ARM_OP_IMM, ARM_OP_MEM                # noqa: E402

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
av = (BASE / 'dumps' / 'av-cam.bin.bak').read_bytes()
N = len(av)
md = mkdis()

# ---------------------------------------------------------------- strings
print('=== APL / AIC / dma symbols in av-cam.bin ===')
pats = [rb'apl_[a-z_]+', rb'APL_ERR', rb'set_aic', rb'XDMAC', rb'wbi_cmpr', rb'eSRAM']
found = defaultdict(list)
for p in pats:
    for m in re.finditer(p, av):
        lo = max(0, m.start() - 60)
        hi = min(N, m.start() + 90)
        # expand to the printable string containing the match
        s = lo
        while s > 0 and 32 <= av[s - 1] < 127:
            s -= 1
        e = m.start()
        while e < N and 32 <= av[e] < 127:
            e += 1
        txt = av[s:e].decode('ascii', 'replace')
        found[txt[:96]].append(m.start())
for k in sorted(found):
    print('  0x%08x  %s' % (found[k][0], k))
print()

# ------------------------------------------------- PC-relative reference map
print('=== building the PC-relative reference map (PC reg id is 11) ===')
branch_targets = set()
bl_sites = {}
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
    tgt = i + 4 + v
    branch_targets.add(tgt)
    if not (hw1 & 0x0800):
        bl_sites.setdefault(tgt, set()).add(i)

seeds = [t for t in sorted(branch_targets)
         if 0x1000 <= t < 0xAED000 and is_prologue(av, t)]
print('  %d prologue seeds' % len(seeds))

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
                and ops[1].type == ARM_OP_MEM and ops[1].mem.base == 11:
            la = ((addr + 4) & ~3) + ops[1].mem.disp
            if 0 <= la <= N - 4 and ops[0].type == ARM_OP_REG:
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
print('  %d addresses swept, %d resolved targets' % (len(covered), len(users)))
print()

# ------------------------------------------------- who references the APL strings
print('=== functions referencing the APL/AIC strings ===')
apl_strings = {}
for k, v in found.items():
    for off in v:
        apl_strings[off] = k

interesting = []
for off, txt in apl_strings.items():
    hits = users.get(off, [])
    for fn, pc in hits:
        interesting.append((fn, off, txt))
interesting.sort()
seen_fn = set()
for fn, off, txt in interesting:
    if fn in seen_fn:
        continue
    seen_fn.add(fn)
    print('  fn 0x%08x  <- "%s"' % (fn, txt[:70]))
print('  %d distinct functions' % len(seen_fn))
