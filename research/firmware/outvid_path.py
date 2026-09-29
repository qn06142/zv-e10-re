"""Two open questions:
  1. Is there a call path from the per-frame ring-buffer function to 0xB73C0
     (the function that receives the computed pixel buffer in r2)?
  2. What is 1060 (0x424)?  Corroborate it as a stride or refute it.
"""
import struct
from collections import defaultdict, deque
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
av = (BASE / 'dumps' / 'av-cam.bin.bak').read_bytes()
N = len(av)
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)

TARGET = 0x000B73C0          # receives the buffer address in r2
RING = 0x000B98BC            # references sfmc_dec_ring_buffer_with_pts.cpp
RING_CALLERS = [0x6A8B1A, 0x6A8B46, 0x6A8B6E]
B7688 = 0x000B7688
OUTVID = [0x000b6e78, 0x000b6f68, 0x000b7128, 0x000b71aa, 0x000b7230,
          0x000b7358, 0x000b73c0, 0x000b7688, 0x000b78ec, 0x000b79b4,
          0x000b818c, 0x000b82b8]

# ---- build the call graph ------------------------------------------------
callees_of = defaultdict(set)      # call site -> target
callers_of = defaultdict(set)      # target -> call sites
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
    tgt = i + 4 + v
    branch_targets.add(tgt)
    if not (hw1 & 0x0800):        # BL, not B.W
        callees_of[i].add(tgt)
        callers_of[tgt].add(i)

print('call graph: %d call sites, %d distinct targets' % (len(callees_of), len(callers_of)))
print()


def dis1(buf, addr):
    for extra in (b'', b'\x00' * 4, b'\x00' * 8, b'\x00' * 16):
        for i in md.disasm(bytes(buf) + extra, addr):
            return i
    return None


def fn_start(site, back=0x2000):
    """Nearest preceding prologue of ANY recognised kind (16-bit push with LR,
    or 32-bit push.w / stmdb).  Scan backwards and take the closest match -
    checking 16-bit before 32-bit would skip over push.w prologues."""
    for a in range(site - 2, max(0, site - back), -2):
        if a + 4 > N:
            continue
        hw = struct.unpack_from('<H', av, a)[0]
        if (hw & 0xFF00) == 0xB500 and (hw & 0x80):
            return a
        hw1 = struct.unpack_from('<H', av, a)[0]
        if hw1 == 0xE92D or (hw1 & 0xFF00) == 0xE800 or (hw1 & 0xFE00) == 0xE800:
            return a
    return None


def callees_from_fn(start, limit=0x4000):
    out = set()
    addr = start
    n = 0
    while addr < start + limit and n < 4000:
        i = dis1(av[addr:addr + 4], addr)
        if i is None:
            break
        if i.mnemonic == 'bl':
            try:
                out.add(int(i.op_str.split('#')[-1], 16))
            except ValueError:
                pass
        addr += i.size
        n += 1
        if i.mnemonic in ('pop', 'bx') and 'pc' in i.op_str:
            break
    return out


# ---- Q1: path from the ring-buffer caller to 0xB73C0 ---------------------
print('=== Q1: is 0xB73C0 reachable from the per-frame ring-buffer function? ===')
rstart = fn_start(RING)
holder = fn_start(RING_CALLERS[0])
print('  ring buffer fn: %s   its callers at %s' % (
    ('0x%08x' % rstart) if rstart else 'NOT FOUND',
    ' '.join('0x%06x' % c for c in RING_CALLERS)))
print('  enclosing fn of those call sites: %s' % (
    ('0x%08x' % holder) if holder else 'NOT FOUND'))
print()

# BFS forward from the ring function through known function boundaries
def bfs_path(src, dst, maxdepth=8):
    seen = {src: None}
    q = deque([(src, 0)])
    while q:
        f, d = q.popleft()
        if d >= maxdepth:
            continue
        for cs in sorted(callers_of.get(f, ())):
            pass
        # find callees by walking this function
        for c in callees_from_fn(f):
            if c in seen:
                continue
            seen[c] = f
            if c == dst:
                path = [c]
                while seen[path[-1]] is not None:
                    path.append(seen[path[-1]])
                return list(reversed(path))
            q.append((c, d + 1))
    return None


p1 = bfs_path(rstart, TARGET) if rstart else None
print('  ring 0x%08x -> 0x%08x : %s' % (rstart or 0, TARGET, (
    ' -> '.join('0x%08x' % x for x in p1) if p1 else 'NO PATH FOUND')))
p2 = bfs_path(holder, TARGET) if holder else None
print('  holder 0x%08x -> 0x%08x : %s' % (holder or 0, TARGET, (
    ' -> '.join('0x%08x' % x for x in p2) if p2 else 'NO PATH FOUND')))
p3 = bfs_path(RING, TARGET)
print('  ring 0x%08x -> 0x%08x : %s' % (RING, TARGET, (
    ' -> '.join('0x%08x' % x for x in p3) if p3 else 'NO PATH FOUND')))
# also from 0xB7688, which we know computes the buffer
p4 = bfs_path(B7688, TARGET)
print('  0xB7688 -> 0x%08x : %s' % (TARGET, (
    ' -> '.join('0x%08x' % x for x in p4) if p4 else 'NO PATH FOUND')))
print()

# who is at the top - the per-frame root?
print('=== callers of the ring-buffer fn (the per-frame root) ===')
for c in sorted(callers_of.get(rstart, ()))[:10]:
    print('  0x%06x   (enclosing fn 0x%08x)' % (c, fn_start(c) or 0))
print()

print('=== callers of 0xB7688 (the function that computes base+1060*index) ===')
for c in sorted(callers_of.get(B7688, ())):
    print('  0x%06x   (enclosing fn 0x%08x)' % (c, fn_start(c) or 0))
print()

# ---- Q2: what is 1060? ----------------------------------------------------
def decode_movw(hw1, hw2):
    """MOVW T2 (bits9-4 == 100100) and T3 (bits9-4 == 101000).
    imm16 = imm4:i:imm3:imm8   -- imm3 is bits 14-12 of hw2, NOT bit 13."""
    if (hw1 >> 11) != 0b11110:
        return None, None
    tag = (hw1 >> 4) & 0x3F
    if tag not in (0b100100, 0b101000):
        return None, None
    if (hw2 >> 15) != 0:
        return None, None
    i = (hw1 >> 10) & 1
    imm4 = hw1 & 0xF
    imm3 = (hw2 >> 12) & 0x7
    rd = (hw2 >> 8) & 0xF
    imm8 = hw2 & 0xFF
    return (imm4 << 12) | (i << 11) | (imm3 << 8) | imm8, rd


def movw_imm(hw1, hw2):
    v, _ = decode_movw(hw1, hw2)
    return v


print('=== Q2: corroborate 0x424 (1060) ===')
print('  self-test on the known encoding at 0xb76ae (40 f2 24 47):')
v, rd = decode_movw(0xf240, 0x4724)
print('    decode -> imm=0x%04x (%d)  rd=r%d   %s' % (
    v, v, rd, 'OK' if v == 0x424 and rd == 7 else 'WRONG'))
print()

hits = []
for i in range(0, N - 4, 2):
    hw1, hw2 = struct.unpack_from('<HH', av, i)
    v, rd = decode_movw(hw1, hw2)
    if v == 0x424:
        hits.append((i, rd))
print('  movw rX, #0x424 found at %d site(s): %s' % (
    len(hits), ' '.join('0x%06x(r%d)' % (h, r) for h, r in hits[:20])))
print()

print('  all MOVW immediates in the output_video region 0xb6000-0xb9000, >= 256:')
seen = defaultdict(list)
for i in range(0xb6000, 0xb9000, 2):
    hw1, hw2 = struct.unpack_from('<HH', av, i)
    v, rd = decode_movw(hw1, hw2)
    if v and v >= 256:
        seen[v].append(i)
for v in sorted(seen):
    print('    0x%05x = %-6d x%d  at %s' % (
        v, v, len(seen[v]), ' '.join('0x%06x' % x for x in seen[v][:4])))
print()
print('  common video dimensions for comparison:')
for name, val in (('640x480 /8', 640), ('720 /2', 720), ('960', 960), ('1280', 1280),
                  ('1920', 1920), ('540*2', 1080), ('1060/2=530', 530)):
    print('    %-12s %d  %s' % (name, val, 'PRESENT' if val in seen else '-'))
print()
print('  1060 = 4*265 = 2*530. If it were a 16-bit line pitch, width would be')
print('  530 px, which matches no standard format -> more likely a block or')
print('  tile pitch than a framebuffer stride. Confirming needs the caller.')
