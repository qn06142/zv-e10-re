"""Disassemble the one function the mod touched, in both versions.

The mod replaced  BL  (ff f7 19 ff)  at 0xaa15a  with  40 f6 50 00.
BL target = 0xaa15a+4-206 = 0xaa090.
So the question is: what does 0xaa090 do, and what happens to callers when
the call to it is gone?  That is why ONLY video playback died.
"""
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

N = 17_289_388
a = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
b = Path(r'F:\restore\av-cam.modded.bin').read_bytes()

PATCH = 0x000aa15a
CALLER_LO = PATCH - 0x60      # show some context before the call
CALLER_HI = PATCH + 0x40

md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
md.detail = False


def dis(buf, lo, hi, base):
    out = []
    for i in md.disasm(buf[lo:hi], base):
        mark = ''
        if i.address <= PATCH < i.address + i.size:
            mark = '   <<<< PATCHED INSTRUCTION'
        out.append('  0x%08x  %-12s %-34s%s' % (i.address, i.bytes.hex(' '), i.mnemonic + ' ' + i.op_str, mark))
    return out


def dis_back(buf, lo, hi, base):
    """Disassemble backwards by trying decreasing start offsets."""
    best = None
    for back in range(1, 8):
        s = lo - back
        if s < 0:
            continue
        chunk = buf[s:hi]
        if len(chunk) < 8:
            continue
        ins = list(md.disasm(chunk, base + (s - lo)))
        # a good alignment consumes the region up to PATCH cleanly
        if ins and any(i.address == base for i in ins) and ins[-1].address + ins[-1].size >= base + (hi - lo) - 4:
            best = (s, ins)
            break
    return best


print('=' * 72)
print('CALLER FUNCTION - vanilla')
print('=' * 72)
for l in dis(a, CALLER_LO, CALLER_HI, CALLER_LO):
    print(l)
print()
print('  call target = 0x%08x' % (PATCH + 4 - 206))
print()
print('=' * 72)
print('CALLER FUNCTION - modded (same region)')
print('=' * 72)
for l in dis(b, CALLER_LO, CALLER_HI, CALLER_LO):
    print(l)
print()
print('=' * 72)
print('THE CALLED FUNCTION at 0xaa090 - vanilla')
print('=' * 72)
for l in dis(a, 0xAA090, 0xAA090 + 0xD0, 0xAA090):
    print(l)
