"""Recover the load base, then redo the RTTI derivation in runtime space.

av-cam.bin has ZERO relocations, so every embedded pointer was resolved at
link time to a RUNTIME address.  The image is XIP-mapped near 0x40000000
(inferred from a UIPC code address at 0x40391eb), so:

    runtime_addr = file_offset + BASE

To find BASE without assuming: the RTTI name pointer must equal
(name_file_offset + BASE).  For each candidate BASE, count how many RTTI names
are explained by a real 4-byte pointer.  The correct BASE will explain
essentially all of them; wrong bases will explain ~none.

That is a self-validating derivation - it does not depend on my 0x40000000
guess being right.
"""
import re
import struct
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from thumb import dis1, mkdis                                                # noqa: E402

BASE_DIR = Path(r'D:\02_Development_And_Projects\pmca-re')
av = (BASE_DIR / 'dumps' / 'av-cam.bin.bak').read_bytes()
N = len(av)
md = mkdis()

names = {}
for m in re.finditer(rb'N\d+[A-Za-z_][A-Za-z0-9_]{4,200}E', av):
    names.setdefault(m.group().decode('latin1'), m.start())
print('=== %d mangled type names ===' % len(names))
print()

# every aligned 4-byte LE word in the image, as a value -> offsets
words = {}
for i in range(0, N - 4, 4):
    v = struct.unpack_from('<I', av, i)[0]
    words.setdefault(v, []).append(i)
print('=== distinct 4-byte words: %d ===' % len(words))
print()

print('=== solve for the load base ===')
print('    For each candidate BASE, how many RTTI name offsets are explained')
print('    by an actual pointer value (name_off + BASE)?')
sample = sorted(names.values())[:400]
best = []
for base in range(0x40000000, 0x40200000, 0x1000):
    hit = 0
    for off in sample:
        if (off + base) in words:
            hit += 1
    if hit > 5:
        best.append((hit, base))
best.sort(reverse=True)
for hit, base in best[:10]:
    print('  BASE 0x%08x explains %d/%d sampled names' % (base, hit, len(sample)))
if not best:
    print('  no BASE in 0x40000000-0x40200000 explains the names; widening search')
    for base in range(0x00000000, 0xC0000000, 0x1000):
        hit = 0
        for off in sample:
            if (off + base) in words:
                hit += 1
        if hit > len(sample) // 4:
            best.append((hit, base))
    best.sort(reverse=True)
    for hit, base in best[:10]:
        print('  BASE 0x%08x explains %d/%d' % (base, hit, len(sample)))
print()

if not best:
    raise SystemExit('could not solve for the load base')

hit, BASE = best[0]
print('=== using BASE 0x%08x (explains %d/%d) ===' % (BASE, hit, len(sample)))
print()

TARGETS = [
    'N3VDF31VdfDisplayCmdSetPanelBrightnessE',
    'N3VDF28VdfDisplayCmdSetPanelReverseE',
    'N3VDF26VdfDisplayCmdSetPanelColorE',
    'N3VDF37VdfDisplayCmdSetPanelColorTemperatureE',
    'N3VDF24VdfDisplayCmdSetOsdAlphaE',
    'N3VDF26VdfDisplayCmdSetMonitorLutE',
    'N3VDF31VdfDisplayCmdGetPanelBrightnessE',
]


def to_file(runtime):
    return runtime - BASE


results = {}
for t in TARGETS:
    off = av.find(t.encode())
    if off < 0:
        continue
    name_rt = off + BASE
    slots = words.get(name_rt, [])
    if not slots:
        print('%s: no pointer to runtime 0x%08x' % (t[:50], name_rt))
        continue
    ti_rt = slots[0]
    ti_file = to_file(ti_rt)
    # typeinfo = [vptr][name]; our name pointer is at ti_file+4, so ti_file = slot-4
    print('%s' % t)
    print('  name file 0x%08x -> runtime 0x%08x' % (off, name_rt))
    print('  name pointer found at file 0x%08x (runtime 0x%08x)' % (ti_rt, slots[0]))
    # find pointers to the typeinfo object
    cand_ti = slots[0] - 4
    ti_refs = words.get(cand_ti + BASE, [])
    if not ti_refs:
        # the pointer we found IS the name field, so typeinfo starts 4 earlier
        ti_refs = words.get(cand_ti, [])
    if not ti_refs:
        print('  no vtable points at the typeinfo')
        continue
    vt_file = ti_refs[0] + 4
    print('  typeinfo file 0x%08x -> vtable file 0x%08x' % (cand_ti, vt_file))
    funcs = []
    k = 0
    while vt_file + 4 * (k + 1) <= N:
        p = struct.unpack_from('<I', av, vt_file + 4 * k)[0]
        # member pointers are RUNTIME addresses, so filter in runtime space
        # using the solved BASE - the earlier 0x40000000 guess rejected all
        # of them and made every vtable look empty.
        if not (BASE + 0x1000 <= p < BASE + N):
            break
        funcs.append((k, to_file(p)))
        k += 1
        if k > 40:
            break
    print('    %d member function(s):' % len(funcs))
    for idx, p in funcs[:12]:
        ins = dis1(md, av[p:p + 4], p)
        print('      [%2d] file 0x%08x  %s' % (
            idx, p, ('%s %s' % (ins.mnemonic, ins.op_str[:40])) if ins else '<undecodable>'))
    results[t] = (vt_file, funcs)
    print()

print('=== summary ===')
for t, (vt, fns) in results.items():
    print('  %-46s vtable 0x%08x  %d member(s)' % (t[:46], vt, len(fns)))
