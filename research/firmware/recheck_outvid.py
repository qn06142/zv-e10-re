"""Re-derive the decoder output-video functions with the corrected walker,
plus a self-test that proves the pop.w fix.

Regression: 0x6B438E starts with `pop.w {r4-r8, sb, sl, pc}`.  The old walker
matched only `mnemonic == 'pop'`, so it sailed straight past that epilogue and
reported a 136-instruction function with 9 calls and 2 memcpy calls - all of
which belonged to the functions that follow.
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from thumb import (mkdis, dis1, is_return, is_prologue, walk, calls_of,  # noqa: E402
                   decode_movw)

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
av = (BASE / 'dumps' / 'av-cam.bin.bak').read_bytes()
N = len(av)
md = mkdis()

print('=== SELF-TEST: the pop.w stop ===')
i = dis1(md, av[0x6B438E:0x6B438E + 4], 0x6B438E)
print('  first insn at 0x6B438E: %-10s %s' % (i.mnemonic, i.op_str))
print('  is_return() says: %s   <- must be True' % is_return(i))
old_style = i.mnemonic in ('pop', 'bx')          # the bug
print('  old buggy test (mnemonic in ("pop","bx")): %s   <- was False, hence the overrun' % old_style)
ins = walk(md, av, 0x6B438E, 0x800)
print('  corrected walk length: %d insn  (was 136)' % len(ins))

# second trap: a PC-relative literal load must NOT look like a return
j = dis1(md, av[0xB76A2:0xB76A2 + 4], 0xB76A2)
print()
print('  second trap, at 0xB76A2: %-10s %s' % (j.mnemonic, j.op_str))
print('  is_return() says: %s   <- must be False ("pc" appears but is a literal source)'
      % is_return(j))
ins2 = walk(md, av, 0xB7688, 0x2000)
print('  corrected walk of 0xB7688: %d insns, ends 0x%08x  (was wrongly 9)'
      % (len(ins2), ins2[-1].address + ins2[-1].size))
assert is_return(i) and not old_style and len(ins) <= 2, 'trap-1 fix not effective'
assert not is_return(j), 'trap-2 fix not effective'
assert len(ins2) > 50, 'trap-2 fix not effective (walk too short)'
print()
print('  BOTH FIXES CONFIRMED')
print()

# ---- enumerate the output_video functions correctly -----------------------
print('=== sfmc_dec_output_video.cpp functions, corrected extents ===')
SEEDS = [0x000b6e78, 0x000b6f68, 0x000b7128, 0x000b71aa, 0x000b7230,
         0x000b7358, 0x000b73c0, 0x000b7688, 0x000b78ec, 0x000b79b4,
         0x000b818c, 0x000b82b8, 0x000b98bc]
for f in SEEDS:
    ins = walk(md, av, f, 0x2000)
    if not ins:
        print('  0x%08x  <no disassembly>' % f)
        continue
    end = ins[-1].address + ins[-1].size
    cl = calls_of(ins)
    stores = [i for i in ins if i.mnemonic.split('.')[0].startswith('str')]
    logs = sum(1 for c in cl if c == 0x7E8E88)
    real_ret = is_return(ins[-1])
    print('  0x%08x..0x%08x %5d B %4d insns  calls=%-3d (logger x%d)  stores=%-3d  ends_at_return=%s'
          % (f, end, end - f, len(ins), len(cl), logs, len(stores), real_ret))
print()

# ---- who calls 0xB73C0, and do those call sites land in real functions? ----
print('=== callers of 0xB73C0, each mapped to its enclosing function ===')
TARGET = 0xB73C0
callers = []
for a in range(0, N - 4, 2):
    from thumb import bl_target
    if bl_target(av, a) == TARGET:
        callers.append(a)
print('  %d call site(s)' % len(callers))
for c in callers:
    # enclosing function = nearest preceding prologue that walks past `c`
    enc = None
    x = c - 2
    while x > c - 0x3000 and x > 0:
        if is_prologue(av, x):
            body = walk(md, av, x, 0x3000)
            if any(i.address == c for i in body):
                enc = x
                break
        x -= 2
    if enc is None:
        # fall back: nearest prologue of any kind
        x = c - 2
        while x > c - 0x3000 and x > 0:
            if is_prologue(av, x):
                enc = x
                break
            x -= 2
    print('    call 0x%06x -> enclosing fn %s' % (c, ('0x%08x' % enc) if enc else 'UNKNOWN'))
print()

# ---- any function in the decoder that calls APL-ish low bands ------------
print('=== decoder functions calling the low helper bands (APL/XDMAC candidates) ===')
BANDS = [(0x6B4000, 0x6B4500, '0x6B40xx buffer layer'),
         (0x6BD000, 0x6BE000, '0x6BDxxx'),
         (0x52E000, 0x530000, '0x52Exxx memcpy family'),
         (0x6AE000, 0x6AF000, '0x6AExxx')]
DEC_LO, DEC_HI = 0xA0000, 0xBA000
found = defaultdict(set)
for a in range(DEC_LO, DEC_HI, 2):
    from thumb import bl_target
    t = bl_target(av, a)
    if t is None:
        continue
    for lo, hi, name in BANDS:
        if lo <= t < hi:
            found[name].add(a)
for lo, hi, name in BANDS:
    s = sorted(found[name])
    print('  %-24s %3d call site(s)  %s' % (name, len(s),
                                             ' '.join('0x%06x' % x for x in s[:10])))
