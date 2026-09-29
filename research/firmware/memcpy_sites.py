"""Find the real plane writers: every memcpy(0x52E120) call site inside the
decoder's address range, and what function each belongs to.

Also fixes a bug that has corrupted several earlier results: capstone reports
`pop.w`, not `pop`, so a walk stopping on mnemonic == 'pop' never stopped and
attributed the following functions' instructions to the previous one.
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

MEMCPY = 0x52E120
DEC_LO, DEC_HI = 0xA0000, 0xBA000          # dec/ modules live here


def dis1(buf, addr):
    for extra in (b'', b'\x00' * 4, b'\x00' * 8, b'\x00' * 16):
        for i in md.disasm(bytes(buf) + extra, addr):
            return i
    return None


def is_return(i):
    """True for any 'pop'/'bx'/'ldm' variant that ends the function."""
    base = i.mnemonic.split('.')[0]
    if base in ('bx',):
        return True
    if base in ('pop', 'ldm', 'ldmia', 'ldmdb', 'ldmda', 'ldmia') and 'pc' in i.op_str:
        return True
    return False


# ---- all memcpy call sites, globally --------------------------------------
sites = []
for i in range(0, N - 4, 2):
    hw1, hw2 = struct.unpack_from('<HH', av, i)
    if hw1 & 0xF800 != 0xF000 or (hw1 & 0xF000) != 0xF000 or (hw1 & 0x0800):
        continue
    s = (hw1 >> 10) & 1
    imm10 = hw1 & 0x3FF
    j1, j2 = (hw2 >> 13) & 1, (hw2 >> 11) & 1
    imm11 = hw2 & 0x7FF
    i1, i2 = (~(j1 ^ s)) & 1, (~(j2 ^ s)) & 1
    v = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
    if v & 0x1000000:
        v -= 0x2000000
    if i + 4 + v == MEMCPY:
        sites.append(i)
print('memcpy (0x%06X) direct call sites: %d' % (MEMCPY, len(sites)))
indec = [s for s in sites if DEC_LO <= s < DEC_HI]
print('  inside the decoder range 0x%x..0x%x: %d' % (DEC_LO, DEC_HI, len(indec)))
print()

# ---- find the enclosing function of each decoder call site ----------------
# walk backwards to a prologue, but bounded, and prefer the closest one that
# is followed by a coherent function body
def enclosing(site, back=0x3000):
    a = site - 2
    while a > site - back and a > 0:
        hw = struct.unpack_from('<H', av, a)[0]
        hw1 = hw
        if (hw & 0xFF00) == 0xB500 and (hw & 0x80):
            # verify it walks to a return without running past `site`
            addr = a
            ok = False
            for _ in range(4000):
                i = dis1(av[addr:addr + 4], addr)
                if i is None:
                    break
                if addr == site:
                    ok = True
                    break
                if addr > site:
                    break
                if is_return(i):
                    break
                addr += i.size
            if ok:
                return a
        a -= 2
    return None


groups = defaultdict(list)
unresolved = 0
for s in indec:
    f = enclosing(s)
    if f is None:
        unresolved += 1
        continue
    groups[f].append(s)

print('=== decoder memcpy sites grouped by enclosing function ===')
print('  %d function(s), %d unresolved site(s)' % (len(groups), unresolved))
rows = []
for f, ss in groups.items():
    # measure the function properly this time
    addr = f
    n = 0
    calls = []
    stores = 0
    idx_st = 0
    while n < 3000:
        i = dis1(av[addr:addr + 4], addr)
        if i is None:
            break
        n += 1
        if i.mnemonic == 'bl':
            try:
                calls.append(int(i.op_str.split('#')[-1], 16))
            except ValueError:
                pass
        if i.mnemonic.startswith('str'):
            stores += 1
            if any(o.type == ARM_OP_MEM and o.mem.index for o in i.operands):
                idx_st += 1
        if is_return(i):
            break
        addr += i.size
    end = addr
    rows.append((len(ss), f, end, n, stores, idx_st, calls))

rows.sort(key=lambda r: -r[0])
for nmem, f, end, n, stores, idx_st, calls in rows[:16]:
    print()
    print('  fn 0x%08x .. 0x%08x  %4d insns  memcpy x%d  stores=%d idxstores=%d' % (
        f, end, n, nmem, stores, idx_st))
    print('     memcpy sites: %s' % ' '.join('0x%06x' % s for s in groups[f][:8]))
    print('     calls: %s' % ' '.join('0x%06x' % c for c in calls[:14]))
