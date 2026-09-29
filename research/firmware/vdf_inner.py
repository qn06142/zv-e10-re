"""Inside the VDF panel commands: find a callable low-level display setter.

vdf_strref3.py resolved 35 of 36 Execute/Activate methods.  Now I need the
innermost call -- the thing that actually writes a panel register -- because
Execute/Activate take (this, MsgAccessorIf*, SubsystemAccessorIf*) and I
cannot fabricate those interface pointers.

Strategy: dump the panel methods, follow their call graph 2 levels deep, and
look for
  * a small leaf that takes an integer and does a str to a peripheral
  * a load from a GLOBAL (the VDF display singleton) I can capture
  * a VDF_* string naming the actual register/op

Also fix the function-start detection: `pop.w {...,pc}` is an EPILOGUE and was
being accepted as a prologue, which is why SetOsdAlpha::Activate "resolved" to
a single pop instruction.
"""
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from thumb import mkdis, dis1, walk, calls_of, is_return                    # noqa: E402
from capstone.arm import ARM_OP_REG, ARM_OP_MEM, ARM_OP_IMM, ARM_REG_PC      # noqa: E402

BASE = 0x635C6000
av = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
N = len(av)
md = mkdis()

FUNCS = {
    'SetPanelReverse::Activate':  0x00151cba,
    'SetOsdAlpha::Execute':      0x00150a9c,
    'SetPanelOsdLuminance::Execute': 0x00151360,
    'SetPanelOutPin::Execute':   0x00151450,
    'SetLineOutPin::Execute':    0x0015038c,
}


def true_entry(lo, hi=0x300):
    """Nearest plausible ENTRY at or before lo: a push that SAVES lr."""
    for q in range(lo, max(0x1000, lo - hi), -2):
        hw = struct.unpack_from('<H', av, q)[0]
        if (hw & 0xFF00) == 0xB500 and (hw & 0x0080):      # push16 {..,lr}
            return q
        if hw == 0xE92D or (hw & 0xFF00) == 0xE800:        # push.w {..,lr}
            return q
    return lo


seen = {}
level2 = defaultdict(list)
for name, ref in sorted(FUNCS.items(), key=lambda kv: kv[1]):
    fn = true_entry(ref)
    body = walk(md, av, fn, 0x1000)
    cl = calls_of(body)
    seen[name] = (fn, cl)
    print('=== %-32s fn 0x%08x  %d insn, %d call(s)' % (name, fn, len(body), len(cl)))
    for i in body[:60]:
        print('   0x%08x  %-9s %-26s' % (i.address, i.mnemonic, i.op_str[:26]))
    print('   calls: %s' % ' '.join('0x%06x' % c for c in cl))
    print()
    for c in cl:
        level2[c].append(name)

print('=== distinct callees across all panel methods ===')
for c, users in sorted(level2.items()):
    b2 = walk(md, av, c, 0x100)
    c2 = calls_of(b2)
    print('  0x%08x  %3d insn  %2d call(s)   from %s'
          % (c, len(b2), len(c2), ', '.join(u[:22] for u in users)))
    if len(b2) <= 14:
        for i in b2:
            print('        0x%08x  %-9s %s' % (i.address, i.mnemonic, i.op_str[:40]))
print()

print('=== small leaves: do any write to a peripheral-looking address? ===')
for c, users in sorted(level2.items()):
    b2 = walk(md, av, c, 0x100)
    if not (1 <= len(b2) <= 14):
        continue
    consts = []
    for i in b2:
        o = i.operands
        for op in o:
            if op.type == ARM_OP_IMM and op.imm >= 0x1000:
                consts.append(op.imm)
            if op.type == ARM_OP_MEM and op.mem.disp >= 0x1000:
                consts.append(op.mem.disp)
    if any(0xC0000000 <= v <= 0xFFFFFFFF for v in consts):
        print('  0x%08x  MMIO?  consts: %s' % (c, [hex(v) for v in consts]))
        for i in b2:
            print('        0x%08x  %-9s %s' % (i.address, i.mnemonic, i.op_str[:44]))
print()

print('=== what strings do these callees log? (VDF_* / register names) ===')
import re                                                       # noqa: E402
for c in sorted(level2):
    b2 = walk(md, av, c, 0x100)
    for i in b2:
        if i.mnemonic.split('.')[0] == 'movw' and i.op_str.startswith('r'):
            pass
# instead: grep the whole image for panel/register-ish VDF strings
for pat in (rb'VDF_[A-Z_]{3,40}', rb'[Pp]anel[A-Za-z_]{0,24}', rb'[Bb]rightness'):
    hits = sorted({m.start() for m in re.finditer(pat, av)})
    print('\n--- pattern %s : %d hits, first 25 ---' % (pat.decode(), len(hits)))
    for h in hits[:25]:
        seg = av[h:h + 40].split(b'\x00')[0].decode('latin1', 'replace')
        print('   0x%08x  %s' % (h, seg))
