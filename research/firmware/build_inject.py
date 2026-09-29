"""Build the injected payload - PROOF ONLY, nothing is flashed.

Site:   /system/av-cam.bin  0xAA15A  (bl #0xa9f90, in dec/sfmc_dec_input_i.cpp)
Cave:   0xBE0000            (inside the 4.90 MB zero run at 0xAEDC95..0xF9A700)

Fixes over the first attempt:
  * iterate the assemble to a FIXED POINT - the instruction length depends on
    the target address, so one "assemble twice" pass is not enough
  * the two adr targets are DIFFERENT (fmt and the src-name string)
  * verify the branch encoding actually assembles, and check its size

Design constraints:
  * B.W is exactly 4 bytes -> same size as the instruction being replaced
  * B.W does not interwork -> the cave must be Thumb
  * load base unknown -> ALL addressing PC-relative (adr / bl / b.w)
  * r0 and r1 must survive: they are the arguments to the original call
  * the logger call is copied verbatim from this function's own error path
    at 0xAA168..0xAA18A; only the format-string pointer differs
"""
import hashlib
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB, KsError

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
SRC = BASE / 'dumps' / 'av-cam.bin.bak'
OUT = BASE / 'dumps' / 'av-cam.injected.bin'

SITE = 0x000AA15A
CAVE = 0x00BE0000
RESUME = 0x000AA160
REAL_CALL = 0x000A9F90
LOGGER = 0x007E8E88
LOGCTX = 0x004402F0

FMT = b'ZVE10PATCH: injected code reached sfmc_dec_input'
SRCNAME = b'av-cam.injected.bin'

ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)


def dis1(buf, addr):
    """Disassemble the first instruction, padding the buffer - capstone can
    refuse a bare 4-byte Thumb-2 word with nothing following it."""
    for extra in (b'', b'\x00\x00\x00\x00', b'\x00' * 8):
        for ins in md.disasm(bytes(buf) + extra, addr):
            return ins
    return None


def build(fmt_addr, src_addr):
    # Argument slots, copied from this function's own error path at
    # 0xAA172..0xAA186:
    #     [sp+8]   = source file name   (literal 0xaa198)
    #     [sp+0xc] = line number        (0x109 = 265)
    #     [sp+0x10] = printf format      (literal 0xaa19c)
    # The first adr feeds the FILENAME slot, the second the FORMAT slot.
    asm = f"""
        push {{r0, r1}}
        sub  sp, #0x20
        bl   {LOGCTX:#x}
        movs r3, #2
        str  r3, [sp]
        subs r3, #3
        str  r3, [sp, #4]
        movs r1, #0x57
        movs r2, #0
        adr  r3, {src_addr:#x}
        str  r3, [sp, #8]
        movw r3, #0x109
        str  r3, [sp, #0xc]
        adr  r3, {fmt_addr:#x}
        str  r3, [sp, #0x10]
        movs r3, #0
        str  r3, [sp, #0x14]
        movs r3, #1
        bl   {LOGGER:#x}
        add  sp, #0x20
        pop  {{r0, r1}}
        bl   {REAL_CALL:#x}
        b    {RESUME:#x}
    """
    enc, _ = ks.asm(asm, CAVE)
    return bytes(enc)


# ---- iterate to a fixed point -------------------------------------------
blob_at = CAVE + 64
for it in range(10):
    fmt_at = blob_at
    src_at = blob_at + len(FMT) + 1
    code = build(fmt_at, src_at)
    new_blob = (CAVE + len(code) + 3) & ~3
    if new_blob == blob_at:
        break
    blob_at = new_blob
else:
    raise SystemExit('layout did not converge')

pad = blob_at - (CAVE + len(code))
payload = code + b'\x00' * pad + FMT + b'\x00' + SRCNAME + b'\x00'

print('=== payload layout (converged after %d iteration(s)) ===' % (it + 1))
print('  cave           : 0x%08x' % CAVE)
print('  code           : %d bytes (0x%08x..0x%08x)' % (len(code), CAVE, CAVE + len(code) - 1))
print('  pad            : %d bytes' % pad)
print('  fmt  string    : 0x%08x  %r' % (blob_at, FMT.decode()))
print('  src  string    : 0x%08x  %r' % (blob_at + len(FMT) + 1, SRCNAME.decode()))
print('  total          : %d bytes' % len(payload))
assert blob_at >= CAVE + len(code), 'blob overlaps code'
print()

print('=== disassembly ===')
for ins in md.disasm(payload, CAVE):
    kind = 'code' if ins.address < CAVE + len(code) else 'DATA'
    print('  0x%08x  %-12s %-34s %s' % (ins.address, ins.bytes.hex(' '),
                                      ins.mnemonic + ' ' + ins.op_str, kind))
print()

# ---- the 4-byte hook ----------------------------------------------------
print('=== 4-byte hook at 0x%08x ===' % SITE)
van4 = bytes(SRC.read_bytes()[SITE:SITE + 4])
v0 = dis1(van4, SITE)
print('  vanilla : %s   %s %s' % (van4.hex(' '), v0.mnemonic, v0.op_str))

branch = None
for syntax in (f'b.w {CAVE:#x}', f'b {CAVE:#x}', f'bw {CAVE:#x}'):
    try:
        enc, _ = ks.asm(syntax, SITE)
        if enc:
            branch = bytes(enc)
            print('  assembled with %-16r -> %s (%d bytes)' % (syntax, branch.hex(' '), len(branch)))
            break
    except KsError as e:
        print('  %-16r failed: %s' % (syntax, e))
if branch is None:
    raise SystemExit('could not assemble the branch')
assert len(branch) == 4, 'the hook must be exactly 4 bytes, got %d' % len(branch)
d0 = dis1(branch, SITE)
if d0 is None:
    # decode the B.W (T4) by hand and prove the target
    hw1, hw2 = struct.unpack_from('<HH', branch, 0)
    assert hw1 & 0xF800 == 0xF000, 'hook is not a Thumb-2 wide branch'
    s = (hw1 >> 10) & 1
    imm10 = hw1 & 0x3FF
    j1 = (hw2 >> 13) & 1
    j2 = (hw2 >> 11) & 1
    imm11 = hw2 & 0x7FF
    assert (hw2 >> 14) & 0x3 == 2 and (hw2 >> 12) & 1 == 1, 'not a B.W T4'
    i1 = (~(j1 ^ s)) & 1
    i2 = (~(j2 ^ s)) & 1
    v = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
    if v & 0x1000000:
        v -= 0x2000000
    tgt = SITE + 4 + v
    print('  injected: %s   (capstone declined; decoded by hand)' % branch.hex(' '))
    print('            S=%d I1=%d I2=%d imm10=0x%03x imm11=0x%03x' % (s, i1, i2, imm10, imm11))
    print('            offset %+d  ->  target 0x%08x' % (v, tgt))
    assert tgt == CAVE, 'hook targets 0x%08x, expected the cave 0x%08x' % (tgt, CAVE)
else:
    print('  injected: %s   %s %s' % (branch.hex(' '), d0.mnemonic, d0.op_str))
    assert d0.mnemonic.startswith('b'), 'hook is not a branch: %s' % d0.mnemonic
    assert d0.op_str.endswith(hex(CAVE)), 'hook does not target the cave: %s' % d0.op_str
print('  -> 4 bytes, branches to the cave. OK')
print()

# ---- build the image ----------------------------------------------------
before = SRC.read_bytes()
img = bytearray(before)
assert all(b == 0 for b in before[CAVE:CAVE + len(payload)]), 'cave is not all zeros'
img[SITE:SITE + 4] = branch
img[CAVE:CAVE + len(payload)] = payload

diff = [i for i in range(len(img)) if img[i] != before[i]]
runs = []
s = p = diff[0]
for i in diff[1:]:
    if i == p + 1:
        p = i
    else:
        runs.append((s, p + 1))
        s = p = i
runs.append((s, p + 1))
print('=== change summary ===')
print('  %d byte(s) changed in %d run(s):' % (len(diff), len(runs)))
for s, e in runs:
    tag = '  <- the 4-byte hook' if (s, e) == (SITE, SITE + 4) else '  <- the cave payload'
    print('    0x%08x .. 0x%08x  (%d bytes)%s' % (s, e - 1, e - s, tag))
assert runs[0] == (SITE, SITE + 4), 'the first change must be the hook'
print()

OUT.write_bytes(bytes(img))
print('=== output ===')
print('  %s' % OUT)
print('  %d bytes' % len(img))
print('  md5 %s   (injected)' % hashlib.md5(bytes(img)).hexdigest())
print('  md5 %s   (vanilla,  for restore)' % hashlib.md5(before).hexdigest())
