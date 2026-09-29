"""SetPanelBrightness::Execute and the apply chain below it.

Established:
  * vtable slot [5] == Execute   (SetOsdAlpha slot[5]=0x00150A99 resolves to
    Execute=0x00150A9C by its log string; same pattern elsewhere)
  => SetPanelBrightness::Execute = 0x00150BA8
  * Execute reads a value out of the command object (byte at this+1) and calls
    a low-level applier, then posts a message carrying the value.

Goal: find an applier callable as applier(&value) with no interface pointers,
and find where the value is stored so the change is reversible.
"""
import re
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from thumb import mkdis, dis1, walk, calls_of                              # noqa: E402
from capstone.arm import ARM_OP_REG, ARM_OP_MEM, ARM_OP_IMM, ARM_REG_PC      # noqa: E402

BASE = 0x635C6000
av = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
N = len(av)
md = mkdis()


def show(label, fn, limit=70, depth=0):
    body = walk(md, av, fn, 0x1000)
    print('%s%s  fn=0x%08x  %d insn, %d call(s)'
          % ('  ' * depth, label, fn, len(body), len(calls_of(body))))
    for i in body[:limit]:
        print('%s  0x%08x  %-9s %s' % ('  ' * depth, i.address, i.mnemonic, i.op_str[:44]))
    return body


b = show('SetPanelBrightness::Execute', 0x00150ba8)
print()
print('calls: %s' % ' '.join('0x%06x' % c for c in calls_of(b)))
print()

# the appliers SetOsdAlpha::Execute used
for nm, a in (('SetOsdAlpha applier', 0x158f58), ('SetOsdAlpha msgpost', 0x72f47c)):
    bb = show(nm, a, 40, 1)
    print()

print('=== string refs inside these ===')
pend = {}
for addr in range(0x1000, N - 4, 2):
    pass
# just scan the few functions for pc-relative string materialisation
def strings_in(fn, size=0x1000):
    body = walk(md, av, fn, size)
    out = []
    pend = {}
    for i in body:
        ops = i.operands
        if i.mnemonic.split('.')[0] == 'ldr' and len(ops) == 2 \
                and ops[1].type == ARM_OP_MEM and ops[1].mem.base == ARM_REG_PC:
            pool = ((i.address + 4) & ~3) + ops[1].mem.disp
            if 0 <= pool <= N - 4:
                pend[i.address] = struct.unpack_from('<I', av, pool)[0]
        if i.mnemonic.split('.')[0] == 'add' and len(ops) == 2 \
                and ops[1].reg == ARM_REG_PC:
            for k, v in list(pend.items()):
                t = v + ((i.address + 4) & ~3)
                if 0 < t < N:
                    out.append((i.address, t, av[t:t + 48].split(b'\x00')[0]))
                del pend[k]
    return out

for nm, fn in (('Brightness::Execute', 0x00150ba8), ('OsdAlpha applier', 0x158f58)):
    print('--- %s string refs ---' % nm)
    for a, t, s in strings_in(fn):
        print('   0x%08x -> 0x%08x  %s' % (a, t, s.decode('latin1', 'replace')[:60]))
    print()

print('=== search for brightness / panel symbols in the image ===')
for pat in (rb'Brightness[A-Za-z_]{0,20}', rb'PanelBrightness[A-Za-z_]{0,20}',
            rb'[Bb]acklight[A-Za-z_]{0,16}', rb'[Pp]anel_[A-Za-z_]{0,16}'):
    hits = sorted({m.start() for m in re.finditer(pat, av)})
    print('\n--- %s : %d hits ---' % (pat.decode(), len(hits)))
    for h in hits[:18]:
        st = av.rfind(b'\x00', 0, h)
        st = 0 if st < 0 else st + 1
        print('   0x%08x  %s' % (h, av[st:st + 60].split(b'\x00')[0]
                                 .decode('latin1', 'replace')[:70]))
