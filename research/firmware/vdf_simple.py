"""No candidate search. Just probe (raw & ~1) and (raw & ~1) + 2 for every
vtable entry, and report which one has a prologue.  No cleverness, no
validation, no BASE arithmetic in the loop - the caller already converted to
file offsets, and this script re-derives them itself so there is no chance of
double-converting.
"""
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from thumb import dis1, mkdis                                              # noqa: E402

BASE = 0x635C6000
av = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
N = len(av)
md = mkdis()


def is_push16(q):
    if q < 0 or q + 4 > N:
        return False
    hw = struct.unpack_from('<H', av, q)[0]
    return (hw & 0xFF00) == 0xB500 and (hw & 0x0080) != 0


def is_push32(q):
    if q < 0 or q + 4 > N:
        return False
    hw = struct.unpack_from('<H', av, q)[0]
    return hw == 0xE92D or (hw & 0xFF00) == 0xE800


def kind(q):
    if is_push16(q):
        return 'push16'
    if is_push32(q):
        return 'push32'
    return '-'


# find the vtables the same way find_base.py did
words = {}
for i in range(0, N - 4, 4):
    words.setdefault(struct.unpack_from('<I', av, i)[0], []).append(i)

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

print('=== raw slot -> file offset -> prologue check ===')
print()
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
    print('%s   vtable file 0x%08x' % (t, vt))
    k = 0
    while vt + 4 * (k + 1) <= N:
        stored = struct.unpack_from('<I', av, vt + 4 * k)[0]
        if not (BASE + 0x1000 <= stored < BASE + N):
            break
        fo = (stored & ~1) - BASE
        cands = [(fo, kind(fo))]
        c2 = fo + 2
        cands.append((c2, kind(c2)))
        line = '  [%d] stored 0x%08x -> file 0x%08x [%s]' % (k, stored, fo, cands[0][1])
        if cands[0][1] == '-' and cands[1][1] != '-':
            line += '   +2 -> %s' % cands[1][1]
        if cands[0][1] == '-':
            line += '   bytes: %s' % av[fo:fo + 8].hex(' ')
        else:
            i0 = dis1(md, av[fo:fo + 4], fo)
            line += '   %s %s' % (i0.mnemonic, i0.op_str[:36])
        print(line)
        k += 1
        if k > 8:
            break
    print()
