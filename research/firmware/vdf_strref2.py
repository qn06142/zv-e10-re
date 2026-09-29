"""Resolve log-string references using this compiler's actual encoding.

Confirmed from vdf_pat.py (two known-good references, 0x001621b6 and 0x00164f02):

    ldr r0, [pc, #0x180]     ; pool holds  (target - pc_at_add)
    ...
    ldr r1, [pc, #0x180]
    ldr r2, [pc, #0x184]
    add r0, pc               ; pc = (addr + 4) & ~3
    add r1, pc
    add r2, pc               ; <-- the log macro's 3rd string
    movw r3, #0x1e5
    bl  <logger>

So the pool value is PC-RELATIVE, never an absolute address.  The previous
brute-force scan compared pool words against string addresses directly and
matched 0 of 36, which is why it failed.

Single linear pass: track the last literal loaded into each register, and on
`add rX, pc` resolve target = pool_value + ((addr + 4) & ~3).
"""
import re
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from thumb import mkdis, dis1, walk, calls_of, is_prologue                 # noqa: E402
from capstone.arm import ARM_OP_MEM, ARM_REG_PC, ARM_REG_SP                 # noqa: E402
from capstone.arm_const import ARM_REG_R0                                   # noqa: E402

BASE = 0x635C6000
av = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
N = len(av)
TEXT_END = 0xAED000
md = mkdis()

logstr = {}
for m in re.finditer(rb'virtual VDF::VDF_ERR VDF::[A-Za-z]+::(Execute|Activate)\(', av):
    logstr[m.start()] = m.group().decode('latin1')
print('=== %d Execute/Activate log strings ===' % len(logstr))
print()

REG = {}
for i in range(13):
    REG[ARM_REG_R0 + i] = i

# ---- single pass: literal loads + `add rX, pc` ---------------------------
pend = {}                     # reg -> pool value awaiting an `add rX, pc`
strrefs = defaultdict(list)   # file offset -> [(add_site, resolved_target)]
for addr in range(0x1000, min(TEXT_END, N) - 4, 2):
    ins = dis1(md, av[addr:addr + 4], addr)
    if ins is None:
        continue
    ops = ins.operands
    mn = ins.mnemonic.split('.')[0]
    if mn == 'ldr' and len(ops) == 2 and ops[1].type == ARM_OP_MEM \
            and ops[1].mem.base == ARM_REG_PC and ops[0].reg in REG:
        pool = ((addr + 4) & ~3) + ops[1].mem.disp
        if 0 <= pool <= N - 4:
            pend[REG[ops[0].reg]] = (struct.unpack_from('<I', av, pool)[0], addr)
    elif mn == 'add' and len(ops) == 2 and ops[1].reg == ARM_REG_PC \
            and ops[0].reg in REG:
        e = pend.pop(REG[ops[0].reg], None)
        if e is not None:
            val, _ = e
            tgt = val + ((addr + 4) & ~3)
            if 0 < tgt < N:
                strrefs[tgt - BASE].append(addr)
    if len(pend) > 24:
        pend.clear()

print('  resolved %d distinct string targets from pc-relative refs' % len(strrefs))
print()

print('=== Execute/Activate log strings -> containing functions ===')
resolved = {}
for soff, s in sorted(logstr.items()):
    hits = strrefs.get(soff)
    if not hits:
        print('  %-52s  UNRESOLVED' % s.split('(')[0].strip().split()[-1][:52])
        continue
    name = s.split('(')[0].strip().split()[-1]
    site = hits[0]
    fn = site
    for q in range(site, max(0x1000, site - 0x400), -2):
        if is_prologue(av, q):
            fn = q
            break
    body = walk(md, av, fn, 0x800)
    cl = calls_of(body)
    resolved[name] = (fn, cl, site)
    print('  %-52s fn 0x%08x  ref@0x%08x  %3d insn, %2d call(s)'
          % (name[:52], fn, site, len(body), len(cl)))

print()
print('=== %d of %d resolved ===' % (len(resolved), len(logstr)))
print()

panel = sorted(n for n in resolved
               if any(w in n for w in ('Panel', 'Osd', 'Luminance', 'Lut', 'Brightness')))
print('=== panel / OSD methods: %d ===' % len(panel))
for n in panel:
    print('  %-52s 0x%08x' % (n[:52], resolved[n][0]))
print()

print('=== logger macro: what does each method log? ===')
for n in panel:
    fn, cl, site = resolved[n]
    # the macro passes (r0=file, r1=func, r2=signature) - recover all three
    got = []
    for off2, sites2 in strrefs.items():
        if any(abs(s2 - site) <= 8 for s2 in sites2) and off2 != 0:
            txt = av[off2:off2 + 60].split(b'\x00')[0]
            got.append((off2, txt.decode('latin1', 'replace')))
    print('\n  %s  (fn 0x%08x)' % (n[:52], fn))
    for o, t in got:
        print('     0x%08x  %s' % (o, t[:70]))
