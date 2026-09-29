"""Read 0xB9D9E (the memcpy call inside the ring-buffer function) directly.

The linear walk from 0xB98BC desynchronised - 540 instructions over 1330
bytes strongly suggests it decoded an embedded literal pool as code and never
reached this site.  Disassembling a window directly avoids trusting the walk,
but the window edges may themselves be misaligned, so the real instruction
containing the call is located from the BL encoding itself.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from thumb import mkdis, dis1, bl_target                                # noqa: E402

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
av = (BASE / 'dumps' / 'av-cam.bin.bak').read_bytes()
N = len(av)
md = mkdis()

# every BL into the memcpy family, with its exact address
sites = [a for a in range(0, N - 4, 2) if (lambda t: t and 0x52E000 <= t < 0x530000)(bl_target(av, a))]
print('memcpy-family BL sites in the whole image: %d' % len(sites))
for a in sites:
    t = bl_target(av, a)
    print('  0x%08x -> 0x%08x' % (a, t))
print()

SITE = 0x0B9D9E
if SITE not in sites:
    cand = [a for a in sites if abs(a - SITE) < 0x40]
    print('NOTE: 0x%08x not an exact site; nearest are %s' % (SITE, [hex(c) for c in cand]))
    if cand:
        SITE = cand[0]
print('=== window around the memcpy call at 0x%08x ===' % SITE)
addr = SITE - 0x50
n = 0
while addr < SITE + 0x20 and n < 90:
    i = dis1(md, av[addr:addr + 4], addr)
    if i is None:
        print('  0x%08x  <undecodable>' % addr)
        addr += 2
        n += 1
        continue
    flag = ''
    if addr == SITE:
        flag = '   <<<<<< memcpy'
    elif i.mnemonic in ('mov', 'movs', 'ldr', 'ldrd') and 'pc' not in i.op_str:
        dst = i.op_str.split(',')[0].strip()
        if dst in ('r0', 'r1', 'r2', 'r3'):
            flag = '   <-- sets %s' % dst
    print('  0x%08x  %-12s %-34s%s' % (addr, i.bytes.hex(' '),
                                        i.mnemonic + ' ' + i.op_str, flag))
    if addr == SITE:
        break
    addr += i.size
    n += 1
print()
t = bl_target(av, SITE)
print('memcpy target 0x%08x' % t)
print('args: r0=dst r1=src r2=len r3=0   (per the memcpy body at 0x52E120:')
print('       cbnz r3 / cbnz r2 / cmp r1,#0 / cmp r0,#0 guard, then bl 0x52E180)')
