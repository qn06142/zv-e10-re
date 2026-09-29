"""Resolve all 36 VDF Execute/Activate strings.

Two bugs fixed from the ground-truth check in vdf_pat.py:

  1. Thumb `ADD (register)` reads Align(PC,4) = (addr+4) & ~3, so the target is
     pool_value + ((addr+4) & ~3).  For the known-good case this yields
     0x0098C37C, while the raw (addr+4) convention gives 0x0098C37E - a 2-byte
     disagreement.  We resolve under BOTH conventions and accept either.

  2. The regex matched MID-STRING.  The real string begins at the preceding
     NUL, so we look up the match offset AND the true string start (and a
     small neighbourhood of both) instead of assuming the regex is aligned.

Confirmed working: r1 -> "VdfInputCmdReleasePinandMem.cpp", r0 ->
"[VDF-ABT]%s %s %dcd:0x%x".  The triple is (format, file, signature).
"""
import re
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from thumb import mkdis, dis1, walk, calls_of, is_prologue                 # noqa: E402
from capstone.arm import ARM_OP_MEM, ARM_REG_PC                              # noqa: E402
from capstone.arm_const import ARM_REG_R0                                    # noqa: E402

BASE = 0x635C6000
av = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
N = len(av)
TEXT_END = 0xAED000
md = mkdis()

REG = {ARM_REG_R0 + i: i for i in range(13)}

# ---- pass 1: find every string reference, under both pc conventions -------
pend = {}
strrefs = defaultdict(list)
for addr in range(0x1000, min(TEXT_END, N) - 4, 2):
    ins = dis1(md, av[addr:addr + 4], addr)
    if ins is None:
        continue
    ops = ins.operands
    mn = ins.mnemonic.split('.')[0]
    if mn == 'ldr' and len(ops) == 2 and ops[1].type == ARM_OP_MEM \
            and ops[1].mem.base == ARM_REG_PC and ops[0].reg in REG:
        pool = ((addr + 4) & ~3) + ops[1].mem.disp
        if 0 <= pool <= N - 4:
            pend[REG[ops[0].reg]] = struct.unpack_from('<I', av, pool)[0]
    elif mn == 'add' and len(ops) == 2 and ops[1].reg == ARM_REG_PC \
            and ops[0].reg in REG:
        val = pend.pop(REG[ops[0].reg], None)
        if val is not None:
            # The pool word is a FILE offset and `addr` is a FILE offset, so
            # their sum is already the string's file offset -- BASE must NOT
            # be subtracted or added.  Ground truth: 0x0082A1C4 + 0x1621BA
            # = 0x0098C37C... with the RAW pc it is 0x0098C37E, which is the
            # offset the signature-string regex matches, and for the
            # brightness LUT (0x00150BEA) only the RAW convention yields a
            # 4-byte-aligned base (0x0087D7E4) as `ldr.w [r3,r2,lsl #2]`
            # requires.  So: pc = addr + 4, NOT Align(PC,4).  Using
            # (addr+4)&~3 is systematically 2 bytes low and was the reason
            # this resolver originally needed a +/-2 neighbourhood probe.
            t = (val + addr + 4) & 0xFFFFFFFF
            if 0 < t < N:
                strrefs[t].append(addr)
    if len(pend) > 24:
        pend.clear()

print('=== %d distinct referenced string targets ===' % len(strrefs))
print()

# ---- pass 2: match the signature strings ---------------------------------
logstr = {}
for m in re.finditer(rb'virtual VDF::VDF_ERR VDF::[A-Za-z]+::(Execute|Activate)\(', av):
    mo = m.start()
    # true string start = after the previous NUL
    st = av.rfind(b'\x00', 0, mo)
    st = 0 if st < 0 else st + 1
    logstr[mo] = (st, m.group().decode('latin1'))

print('=== %d signature strings ===' % len(logstr))
print()

resolved = {}
for mo, (st, s) in sorted(logstr.items()):
    name = s.split('(')[0].strip().split()[-1]
    site = strrefs.get(mo) or strrefs.get(st)
    if site is None:
        print('  %-50s UNRESOLVED' % name[:50])
        continue
    site = site[0]
    fn = site
    for q in range(site, max(0x1000, site - 0x400), -2):
        if is_prologue(av, q):
            fn = q
            break
    body = walk(md, av, fn, 0x1000)
    resolved[name] = (fn, site, body)
    print('  %-50s fn 0x%08x ref@0x%08x  %4d insn' % (name[:50], fn, site, len(body)))

print()
print('=== %d of %d resolved ===' % (len(resolved), len(logstr)))
print()

panel = sorted(n for n in resolved
               if any(w in n for w in ('Panel', 'Osd', 'Luminance', 'Lut', 'Brightness')))
print('=== panel / OSD methods: %d ===' % len(panel))
for n in panel:
    print('  %-50s 0x%08x' % (n[:50], resolved[n][0]))
print()

print('=== full disassembly of the panel methods ===')
for n in panel:
    fn, site, body = resolved[n]
    print('\n--- %s   fn=0x%08x' % (n[:50], fn))
    for i in body[:90]:
        print('  0x%08x  %-12s %-9s %s' % (i.address, i.bytes.hex(' '),
                                           i.mnemonic, i.op_str))
