"""VDF panel commands: decode members at the masked offset, and find Execute().

The earlier UNALIGNED spam was a bad FILTER, not a bad address.  In a 16-bit
Thumb PUSH (0xB5xx) the register list is bits 7-0; requiring LR (0x80) there
rejected `push {r0}` (0xB510), which is a perfectly normal function start.
So: entry = (stored & ~1) - BASE, full stop.  No prologue search.

Also: the long "virtual VDF::VDF_ERR ...::Execute(...)" strings are LOG
strings, not RTTI names, so they ARE referenced PC-relative and will resolve
to the real Execute methods.
"""
import re
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from thumb import mkdis, dis1, is_return, is_prologue, walk, calls_of       # noqa: E402
from capstone.arm import ARM_OP_REG, ARM_OP_IMM, ARM_OP_MEM                 # noqa: E402

BASE = 0x635C6000
av = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
N = len(av)
md = mkdis()

words = {}
for i in range(0, N - 4, 4):
    words.setdefault(struct.unpack_from('<I', av, i)[0], []).append(i)


def members(t):
    off = av.find(t.encode())
    if off < 0:
        return None
    slots = words.get(off + BASE, [])
    if not slots:
        return None
    ti = slots[0] - 4
    refs = words.get(ti + BASE, []) or words.get(ti, [])
    if not refs:
        return None
    vt = refs[0] + 4
    out = []
    k = 0
    while vt + 4 * (k + 1) <= N:
        stored = struct.unpack_from('<I', av, vt + 4 * k)[0]
        if not (BASE + 0x1000 <= stored < BASE + N):
            break
        out.append((k, stored, (stored & ~1) - BASE))
        k += 1
        if k > 8:
            break
    return vt, out


WANT = [
    'N3VDF28VdfDisplayCmdSetPanelReverseE',
    'N3VDF31VdfDisplayCmdSetPanelBrightnessE',
    'N3VDF26VdfDisplayCmdSetPanelColorE',
    'N3VDF37VdfDisplayCmdSetPanelColorTemperatureE',
    'N3VDF24VdfDisplayCmdSetOsdAlphaE',
    'N3VDF26VdfDisplayCmdSetMonitorLutE',
]

print('=== vtable members, decoded at (stored & ~1) - BASE ===')
allm = {}
for t in WANT:
    r = members(t)
    if not r:
        print('\n%s : unresolved' % t)
        continue
    vt, ms = r
    allm[t] = (vt, ms)
    print('\n%s' % t)
    print('  vtable file 0x%08x' % vt)
    for k, stored, fo in ms:
        i0 = dis1(md, av[fo:fo + 4], fo)
        body = walk(md, av, fo, 0x200)
        cl = calls_of(body)
        print('    [%d] file 0x%08x  %-8s %-26s  %3d insn, %d call(s)'
              % (k, fo, i0.mnemonic if i0 else '?',
                 (i0.op_str[:24] if i0 else ''), len(body), len(cl)))
        if cl:
            print('        calls: %s' % ' '.join('0x%06x' % c for c in cl[:10]))

print()
print('=== shared slots across all classes (base-class virtuals) ===')
c = Counter() if False else defaultdict(list)
for t, (vt, ms) in allm.items():
    for k, stored, fo in ms:
        c[(k, fo)].append(t)
for (k, fo), ts in sorted(c.items(), key=lambda x: -len(x[1])):
    if len(ts) > 1:
        i0 = dis1(md, av[fo:fo + 4], fo)
        print('  slot [%d] file 0x%08x  %s %s   (%d classes)'
              % (k, fo, i0.mnemonic if i0 else '?', i0.op_str[:30] if i0 else '', len(ts)))
print()

print('=== Execute() log strings: real code references ===')
for m in re.finditer(rb'virtual VDF::VDF_ERR[^\x00]{0,150}', av):
    s = m.group().decode('latin1')
    print('  0x%08x  %s' % (m.start(), s[:120]))
