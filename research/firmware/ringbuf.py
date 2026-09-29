"""0xB98BC - the ring_buffer_with_pts function: 540 insns, 108 stores, and it
calls memcpy.  Find the memcpy call(s) and identify which argument is the
destination, so a hook can scribble into the frame it just wrote.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from thumb import mkdis, dis1, is_return, is_prologue, walk, calls_of  # noqa: E402
from capstone.arm import ARM_OP_REG, ARM_OP_IMM, ARM_OP_MEM             # noqa: E402

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
av = (BASE / 'dumps' / 'av-cam.bin.bak').read_bytes()
N = len(av)
md = mkdis()

FN = 0xB98BC
MEMCPY_BAND = (0x52E000, 0x530000)

ins = walk(md, av, FN, 0x2000)
print('function 0x%08x: %d insns, ends 0x%08x' % (FN, len(ins), ins[-1].address + ins[-1].size))
print()

# all memcpy-family call sites inside this function
mc = [i for i in ins if i.mnemonic == 'bl'
      and any(lo <= int(i.op_str.split('#')[-1], 16) < hi
              for lo, hi in [MEMCPY_BAND]
              if i.op_str.split('#')[-1].startswith('0x'))]
print('memcpy-family call sites in this function: %s' % ', '.join('0x%06x' % i.address for i in mc))
print()

for site in mc:
    tgt = int(site.op_str.split('#')[-1], 16)
    print('=== memcpy call at 0x%08x -> 0x%08x ===' % (site.address, tgt))
    idx = ins.index(site)
    lo = max(0, idx - 22)
    for i in ins[lo:idx + 8]:
        flag = '   <<<< memcpy' if i.address == site.address else ''
        if i.mnemonic in ('mov', 'movw', 'movs', 'ldr', 'add', 'addw', 'ldrd', 'sub'):
            pass
        print('  0x%08x  %-12s %-34s%s' % (i.address, i.bytes.hex(' '),
                                            i.mnemonic + ' ' + i.op_str, flag))
    print()

# what are the biggest constants used - width/height/stride hints?
print('=== register usage summary: which regs are written before the memcpy ===')
for site in mc:
    idx = ins.index(site)
    window = ins[max(0, idx - 22):idx]
    last = {}
    for i in window:
        o = i.op_str
        stem = i.mnemonic.split('.')[0]
        if stem in ('mov', 'movs', 'movw', 'ldr', 'ldrd', 'add', 'addw', 'sub', 'ldr.w', 'ldrd'):
            dst = o.split(',')[0].strip()
            last[dst] = '%s %s' % (i.mnemonic, o)
    for r in ('r0', 'r1', 'r2', 'r3'):
        print('  %s <- %s' % (r, last.get(r, '(not set in the window)')))
    print()

print('=== all distinct call targets in this function ===')
cl = calls_of(ins)
seen = []
for c in cl:
    if c not in seen:
        seen.append(c)
print('  %s' % ' '.join('0x%06x' % c for c in seen))
