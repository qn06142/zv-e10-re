"""Find the decoder's video-output / YC-pin setup code in av-cam.bin.

Target: a function we can hook that runs PER FRAME and that has the output
buffer address in hand, so the payload can scribble a pattern into the
decoded picture.

Method: the module strings sit at known addresses. Sony references them
PC-relative (ldr rX,[pc,#imm] ; add rX,pc), so walk every PC-relative literal
load in the code and resolve it - that gives the set of literal addresses
actually used, and the functions that use them.
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

WANT = {
    'dec/sfmc_dec_output_video.cpp': None,
    'dec/sfmc_dec_yc_pin.cpp': None,
    'dec/sfmc_dec_output.cpp': None,
    'dec/sfmc_dec_output_i.cpp': None,
    'dec/sfmc_dec_input_video.cpp': None,
    'dec/sfmc_dec_ring_buffer_with_pts.cpp': None,
}
for name in WANT:
    i = av.find(name.encode())
    if i >= 0:
        WANT[name] = i

print('=== target source strings ===')
for k, v in WANT.items():
    print('  %-42s %s' % (k, ('0x%08x' % v) if v is not None else 'NOT FOUND'))
print()

# ---- collect all PC-relative literal loads, and which function used them ----
# function seeds: branch targets that look like prologues
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

seeds = []
for t in sorted(branch_targets):
    if not (0x1000 <= t < 0xAED000) or t + 2 > N:
        continue
    hw = struct.unpack_from('<H', av, t)[0]
    hw2 = struct.unpack_from('<H', av, t + 2)[0] if t + 4 <= N else 0
    if ((hw & 0xFF00) == 0xB500 and (hw & 0x80)) or hw == 0xE92D or (hw & 0xFF00) == 0xB500:
        seeds.append(t)
seeds = sorted(set(seeds))
print('=== sweeping %d prologue seeds for PC-relative references ===' % len(seeds))


def dis1(buf, addr):
    """First instruction at addr, padding the buffer: capstone refuses a bare
    4-byte Thumb-2 word with nothing following it."""
    for extra in (b'', b'\x00\x00\x00\x00', b'\x00' * 8, b'\x00' * 16):
        for i in md.disasm(bytes(buf) + extra, addr):
            return i
    return None


# users[target_string_addr] = list of (function_start, pc_of_reference)
users = defaultdict(list)
fn_of = {}
covered = set()
MAX_FN = 0x2000

for seed in seeds:
    if seed in covered:
        continue
    pending = {}
    addr = seed
    limit = min(seed + MAX_FN, 0xAED000, N)
    while addr < limit:
        if addr in covered:
            break
        covered.add(addr)
        ins = dis1(av[addr:addr + 4], addr)
        if ins is None:
            break
        ops = ins.operands
        m = ins.mnemonic
        # PC is register id 11 in capstone, NOT 13
        if m.startswith('ldr') and len(ops) == 2 and ops[1].type == ARM_OP_MEM:
            mem = ops[1].mem
            if mem.base == 11:                     # ARM_REG_PC
                la = ((addr + 4) & ~3) + mem.disp
                if 0 <= la <= N - 4:
                    val = struct.unpack_from('<I', av, la)[0]
                    if ops[0].type == ARM_OP_REG:
                        pending[ops[0].reg] = val
        if m in ('add', 'addw', 'adr') and len(ops) >= 2 and ops[1].type == ARM_OP_REG:
            if ops[0].type == ARM_OP_REG and ops[0].reg in pending:
                tgt = pending.pop(ops[0].reg) + (addr + 4)
                if 0 < tgt < N:
                    users[tgt].append((seed, addr))
                    fn_of[tgt] = seed
        if m in ('pop', 'bx', 'ldmdb', 'ldmia') and 'pc' in ins.op_str:
            break
        addr += ins.size

print('  %d addresses swept, %d distinct PC-relative targets' % (len(covered), len(users)))
print()

print('=== which functions reference the decoder output strings? ===')
for name, want in WANT.items():
    if want is None:
        continue
    hits = users.get(want, [])
    print()
    print('  %s   (string at 0x%08x)' % (name, want))
    if not hits:
        print('    no PC-relative reference found in the swept code')
        continue
    fstart = sorted({f for f, _ in hits})
    print('    %d reference(s) from %d function(s): %s' % (
        len(hits), len(fstart), ', '.join('0x%08x' % f for f in fstart[:12])))
    for f, pc in hits[:6]:
        print('      func 0x%08x  ref at 0x%08x' % (f, pc))
