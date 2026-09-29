"""Learn the string-reference encoding from a KNOWN-GOOD case.

vdf_execute.py resolved exactly two of the 36 strings:
    VdfInputReleasePinAndMem::Execute        ref@0x001621b6
    VdfInputCmdUpdateTimeCodePin::Activate   ref@0x00164f02

Those are ground truth.  Dump the bytes around each reference so we can see
precisely how this compiler materialises a string pointer (absolute pool
value? pc-relative pool + add reg,pc? movw/movt pair?), then apply the
confirmed pattern to the panel strings we actually care about.
"""
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from thumb import mkdis, dis1, walk                                      # noqa: E402

BASE = 0x635C6000
av = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
N = len(av)
md = mkdis()

KNOWN = [
    ('VdfInputReleasePinAndMem::Execute', 0x0098c37e, 0x001621b6),
    ('VdfInputCmdUpdateTimeCodePin::Activate', 0x0098ca25, 0x00164f02),
]

for name, soff, ref in KNOWN:
    runtime = soff + BASE
    print('=== %s' % name)
    print('  string file off 0x%08x   runtime 0x%08x' % (soff, runtime))
    print('  literal-load site 0x%08x' % ref)
    print()
    print('  --- 40 bytes before the site ---')
    for a in range(ref - 40, ref, 2):
        i = dis1(md, av[a:a + 4], a)
        print('    0x%08x  %-8s %-22s' % (a, av[a:a + 2].hex(' '),
                                           (i.mnemonic + ' ' + i.op_str) if i else '?'))
    print('  --- 4 bytes at the site ---')
    for a in range(ref, ref + 8, 2):
        i = dis1(md, av[a:a + 4], a)
        print('    0x%08x  %-8s %-22s' % (a, av[a:a + 2].hex(' '),
                                           (i.mnemonic + ' ' + i.op_str) if i else '?'))
    print('  --- 12 bytes after the site ---')
    for a in range(ref + 4, ref + 20, 2):
        i = dis1(md, av[a:a + 4], a)
        print('    0x%08x  %-8s %-22s' % (a, av[a:a + 2].hex(' '),
                                           (i.mnemonic + ' ' + i.op_str) if i else '?'))
    print()

    # find the literal pool entry the site points at, and show its neighbours
    hw = struct.unpack_from('<H', av, ref)[0]
    if (hw & 0xF800) == 0x4800:
        pool = ((ref + 4) & ~3) + (hw & 0xFF) * 4
        print('  LDR-literal: pool file 0x%08x' % pool)
        for p in range(pool - 12, pool + 16, 4):
            v = struct.unpack_from('<I', av, p)[0]
            note = '  <-- this string' if p == pool else ''
            print('    0x%08x  0x%08x%s' % (p, v, note))
    print()

print('=== do the pool values look like offsets or absolute addrs? ===')
for name, soff, ref in KNOWN:
    hw = struct.unpack_from('<H', av, ref)[0]
    if (hw & 0xF800) != 0x4800:
        print('  %s: site is not an LDR-literal (hw=0x%04x)' % (name, hw))
        continue
    pool = ((ref + 4) & ~3) + (hw & 0xFF) * 4
    v = struct.unpack_from('<I', av, pool)[0]
    print('  %s' % name)
    print('     pool 0x%08x = 0x%08x' % (pool, v))
    print('     string runtime = 0x%08x' % (soff + BASE))
    print('     diff string-pool = 0x%08x   (pc-relative if ~ small)' % ((soff + BASE) - v))
