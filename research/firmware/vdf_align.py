"""Align the VDF vtable members to real function entries.

The derivation works (each class has a distinct member set, and slot [2] is
shared across all seven - a base-class virtual).  But the raw slot values do
not decode as prologues, which means either:
  (a) the slot points into the middle of a function (a thunk), or
  (b) the vtable entries are +offset from the true entry (ARM vtables often
      store the function address directly, but Thumb IT blocks may add a
      low bit or the slot may point one word earlier).

Find the true entry: walk backwards from the slot value looking for a
plausible prologue, and validate by disassembling forward to a return.
"""
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from thumb import dis1, mkdis, is_return                                  # noqa: E402
from capstone.arm import ARM_OP_REG, ARM_OP_IMM, ARM_OP_MEM                # noqa: E402

BASE = 0x635C6000
av = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
N = len(av)
md = mkdis()

words = {}
for i in range(0, N - 4, 4):
    words.setdefault(struct.unpack_from('<I', av, i)[0], []).append(i)


def looks_like_entry(p):
    """Does p decode to a coherent function body ending in a return?"""
    if not (0x1000 <= p < 0xAED000):
        return False
    ins = []
    addr = p
    for _ in range(80):
        i = dis1(md, av[addr:addr + 4], addr)
        if i is None:
            return False
        ins.append(i)
        addr += i.size
        if is_return(i):
            return len(ins) >= 2
    return False


def has_prologue_at(p):
    """Is there a function prologue at p?

    The LR test must be on the LOW byte: in a 16-bit Thumb PUSH (0xB5xx) the
    register list occupies bits 7-0, so LR is bit 0x80 of the halfword's low
    byte.  Testing `hw & 0x80` on the 16-bit value tests bit 15, which is
    part of the opcode -- so `push {r4, lr}` (0xB510) was rejected by the very
    check meant to accept it.  That bug is why every vtable entry read as
    UNALIGNED while the raw bytes were visibly correct.
    """
    if not (0x1000 <= p + 4 <= N):
        return False
    hw = struct.unpack_from('<H', av, p)[0]
    if (hw & 0xFF00) == 0xB500 and (hw & 0x0080):
        return True                     # 16-bit PUSH {.., lr}   LR = bit 0x80
    if hw == 0xE92D or (hw & 0xFF00) == 0xE800:
        return True                     # 32-bit PUSH.W / STMDB
    return False


def realign(p):
    """Return the true function start for a vtable entry.

    Established by dumping raw bytes (research/firmware/rawdump.py):
      * every entry has bit0 SET (Thumb marker) -> mask it off first
      * the entry may be masked+2, i.e. the stored word points one halfword
        BEFORE the real prologue

    Validation is by PROLOGUE ONLY.  The earlier version also required the
    body to reach a `return` within 80 instructions, which rejected genuine
    entries: these are small accessors, and a long tail (a switch, or a call
    that never returns on the taken path) legitimately has no return in range.
    Requiring a return turned real functions into UNALIGNED.
    """
    # p arrives already converted to a FILE OFFSET by the caller (pf = p - BASE).
    # The only thing left is the Thumb bit: the stored vtable word has bit0 set,
    # so masking it off yields the real halfword address.  The entry may also
    # sit +2 from that.
    m = p & ~1
    for d in (0, 2, -2, 4, -4, 6, -6, 8, -8):
        q = m + d
        if has_prologue_at(q):
            return q
    return None


TARGETS = [
    'N3VDF31VdfDisplayCmdSetPanelBrightnessE',
    'N3VDF28VdfDisplayCmdSetPanelReverseE',
    'N3VDF26VdfDisplayCmdSetPanelColorE',
    'N3VDF37VdfDisplayCmdSetPanelColorTemperatureE',
    'N3VDF24VdfDisplayCmdSetOsdAlphaE',
    'N3VDF26VdfDisplayCmdSetMonitorLutE',
    'N3VDF31VdfDisplayCmdGetPanelBrightnessE',
    'N3VDF24VdfDisplayCmdGetPanelOutE',
    'N3VDF26VdfDisplayCmdGetPanelColorE',
]

print('=== VDF panel command member functions (BASE 0x%08X) ===' % BASE)
print()
found = {}
for t in TARGETS:
    off = av.find(t.encode())
    if off < 0:
        continue
    slots = words.get(off + BASE, [])
    if not slots:
        continue
    ti = slots[0] - 4
    ti_refs = words.get(ti + BASE, []) or words.get(ti, [])
    if not ti_refs:
        continue
    vt = ti_refs[0] + 4
    rows = []
    k = 0
    while vt + 4 * (k + 1) <= N:
        p = struct.unpack_from('<I', av, vt + 4 * k)[0]
        if not (BASE + 0x1000 <= p < BASE + N):
            break
        pf = p - BASE
        real = realign(pf)
        rows.append((k, pf, real))
        k += 1
        if k > 24:
            break
    print('%s' % t)
    print('  vtable 0x%08x  %d slots' % (vt, len(rows)))
    for idx, pf, real in rows:
        if real is None:
            print('    [%2d] raw 0x%08x  UNALIGNED' % (idx, pf))
        else:
            i0 = dis1(md, av[real:real + 4], real)
            delta = real - pf
            print('    [%2d] raw 0x%08x -> entry 0x%08x (%+d)  %-6s %s'
                  % (idx, pf, real, delta, i0.mnemonic, i0.op_str[:36]))
    found[t] = (vt, rows)
    print()

print('=== the shared slot, which is a base-class virtual ===')
from collections import Counter                                            # noqa: E402
c = Counter()
for t, (vt, rows) in found.items():
    for idx, pf, real in rows:
        if real is not None:
            c[real] += 1
for addr, n in c.most_common(6):
    if n > 1:
        i0 = dis1(md, av[addr:addr + 4], addr)
        print('  0x%08x  used by %d classes  %s %s'
              % (addr, n, i0.mnemonic, i0.op_str[:44]))
print()
print('%d classes resolved' % len(found))
