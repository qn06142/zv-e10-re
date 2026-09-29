"""Index the av-cam.bin symbol table, then locate the VDF display commands.

av-cam.bin carries full C++ mangled names as plain strings (N3VDF31...E), so
the symbol table is recoverable by name.  Locate the panel commands we would
need for a visible, reversible change:

    VdfDisplayCmdSetPanelBrightness     - clearly visible, trivially reversible
    VdfDisplayCmdSetPanelColorTemperature
    VdfDisplayCmdSetPanelColor
    VdfDisplayCmdSetPanelReverse        - inverts the panel: maximal visibility
    VdfDisplayCmdSetOsdAlpha
    VdfDisplayCmdSetMonitorLut

Also record the neighbouring Get* forms, because a Get* tells us the register
map (a Get usually reads back what a Set writes).
"""
import re
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from thumb import mkdis, dis1, is_return, is_prologue, walk, calls_of      # noqa: E402

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
av = (BASE / 'dumps' / 'av-cam.bin.bak').read_bytes()
N = len(av)
md = mkdis()

print('=== how many mangled names are in the image? ===')
names = {}
for m in re.finditer(rb'N\d+[A-Za-z_][A-Za-z0-9_]{4,200}E', av):
    s = m.group().decode('latin1')
    names.setdefault(s, m.start())
print('  %d unique mangled names' % len(names))
print()

VDF = sorted(s for s in names if s.startswith('N3VDF'))
print('=== VDF namespace: %d names ===' % len(VDF))
print()

WANT = [
    'SetPanelBrightness', 'SetPanelColor', 'SetPanelColorTemperature',
    'SetPanelReverse', 'SetOsdAlpha', 'SetMonitorLut', 'SetPanelOut',
    'GetPanelBrightness', 'GetPanelColor', 'GetPanelOut', 'GetDisplayQuality',
]
print('=== the commands we want ===')
hits = {}
for w in WANT:
    matched = [s for s in VDF if w in s]
    hits[w] = matched
    print('  %-26s %d name(s)' % (w, len(matched)))
    for s in matched[:6]:
        print('      0x%08x  %s' % (names[s], s[:100]))
print()

# --- resolve names to code addresses -------------------------------------
# The strings are the mangled type names; the code that logs them uses them
# PC-relative.  Build the reference map, then attribute each name to a
# function.
print('=== building the PC-relative reference map ===')
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
print('  %d prologue seeds' % len(seeds))

from capstone.arm import ARM_OP_REG, ARM_OP_MEM                            # noqa: E402
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
print('  %d addresses swept, %d resolved targets' % (len(covered), len(users)))
print()

print('=== functions referencing the panel command strings ===')
for w in WANT:
    seen_fn = set()
    for s in hits[w][:40]:
        for fn, pc in users.get(names[s], ()):
            if fn in seen_fn:
                continue
            seen_fn.add(fn)
            print('  %-26s fn 0x%08x   <- %s' % (w, fn, s[:64]))
    if not seen_fn:
        print('  %-26s (no PC-relative reference found)' % w)
