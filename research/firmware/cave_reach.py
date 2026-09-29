"""Find code caves by measuring reachability, not by feature association.

Method (sound without symbols):
  1. every address that is the target of a BL or B is 'branch-referenced'
  2. every 32-bit value appearing anywhere in the file is a candidate
     function pointer (vtable slot, dispatch table, state-machine table),
     which also makes its target 'referenced'
  3. a function entry in neither set has no inbound branch and is not
     address-taken -> unreachable -> safe to overwrite

Reports unreachable entries, and specifically whether the golf/HSRec
region is among them.
"""
import struct
from pathlib import Path

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
av = (BASE / 'dumps' / 'av-cam.bin.bak').read_bytes()
N = len(av)

# ---------------------------------------------------------------- branches
branch_targets = set()
n_bl = n_b = 0
for i in range(0, N - 4, 2):
    hw1, hw2 = struct.unpack_from('<HH', av, i)
    if hw1 & 0xF800 != 0xF000:
        continue
    if hw1 & 0x0800:                       # B (T2), 32-bit
        s = (hw1 >> 10) & 1
        imm10 = hw1 & 0x3FF
        j1 = (hw2 >> 13) & 1
        j2 = (hw2 >> 11) & 1
        imm11 = hw2 & 0x7FF
        i1 = (~(j1 ^ s)) & 1
        i2 = (~(j2 ^ s)) & 1
        v = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
        if v & 0x1000000:
            v -= 0x2000000
        branch_targets.add(i + 4 + v)
        n_b += 1
    else:                                  # 16-bit B
        v = hw1 & 0x7FF
        if v & 0x400:
            v -= 0x800
        branch_targets.add(i + 4 + (v << 1))
        n_b += 1
print('=== branch scan ===')
print('  %d branch instructions, %d distinct targets' % (n_b, len(branch_targets)))
print()

# ------------------------------------------------- address-taken candidates
# every aligned 4-byte LE value in the file is a candidate pointer
ptr_vals = set()
for i in range(0, N - 4, 4):
    v = struct.unpack_from('<I', av, i)[0]
    if 0 < v < N:
        ptr_vals.add(v)
print('=== pointer scan ===')
print('  %d distinct 4-byte values in 0..len(file) (candidate pointers)' % len(ptr_vals))
print()

referenced = branch_targets | ptr_vals
print('=== combined referenced set: %d addresses ===' % len(referenced))
print()

# ------------------------------------------------------- candidate entries
def is_push(hw):
    # 16-bit PUSH {..,lr}
    return (hw & 0xFF00) == 0xB500 and (hw & 0x80)


def is_push32(hw1):
    # 32-bit PUSH.W / STMDB
    return hw1 == 0xE92D or (hw1 & 0xFE00) == 0xE800


# The golf log strings cluster here; find code near them and test entries.
STRINGS = {
    'Sequence_HSRecGolfshot.cpp': 0x009c50b4,
    'Stage_EncodeJpeg_GolfShot_THM': 0x009ba5c1,
    '[GOLFSHOT]Seq._GolfBgest': 0x009c53d6,
    '[GOLFSHOT]Seq._GolfSsp': 0x009c575b,
    'Stage_MotionShot_Analysis': 0x009cb53a,
    'MotionShot_Base': 0x009cb554,
}
print('=== are the golf / motionshot string addresses themselves referenced? ===')
for name, off in STRINGS.items():
    print('  %-32s 0x%08x  in referenced set: %s' % (name, off, off in referenced))
print()

# Walk the code section and collect plausible entries, then bucket them.
# Code lives roughly 0x1000..0xAEDC95 (before the big zero hole).
CODE_LO, CODE_HI = 0x1000, 0xAED000
entries = []
i = CODE_LO
while i < CODE_HI:
    hw = struct.unpack_from('<H', av, i)[0]
    if is_push(hw) or is_push32(hw):
        entries.append(i)
        i += 2
    else:
        i += 2
print('=== %d candidate function entries in 0x%x..0x%x ===' % (len(entries), CODE_LO, CODE_HI))

unreach = [e for e in entries if e not in referenced]
print('  %d have NO inbound branch and are NOT address-taken' % len(unreach))
print('  %d are referenced somehow' % (len(entries) - len(unreach)))
print()

# group unreachable entries into runs -> cave candidates
runs = []
if unreach:
    s = p = unreach[0]
    for e in unreach[1:]:
        if e - p <= 0x400:
            p = e
        else:
            runs.append((s, p))
            s = p = e
    runs.append((s, p))
print('=== largest unreachable clusters (cave candidates) ===')
runs.sort(key=lambda t: -(t[1] - t[0]))
for s, e in runs[:10]:
    print('  0x%08x .. 0x%08x   span %d bytes' % (s, e, e - s))
