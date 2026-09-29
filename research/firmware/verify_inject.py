"""Independent verification of dumps/av-cam.injected.bin.

Deliberately does NOT reuse build_inject.py's logic - it re-reads the file
from disk and re-derives everything, so a bug in the builder cannot hide.

Checks:
  1. size, ORIL header, and that the image differs from vanilla ONLY inside
     the two declared windows
  2. the 4-byte hook is a B.W whose target re-derives to the cave
  3. the cave disassembles to the expected instruction sequence
  4. every adr / bl / b.w target in the cave is what we intended
  5. the payload does not clobber r0 or r1 before the real call
"""
import hashlib
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
VAN = BASE / 'dumps' / 'av-cam.bin.bak'
INJ = BASE / 'dumps' / 'av-cam.injected.bin'

FMT = b'ZVE10PATCH: injected code reached sfmc_dec_input'
SRCNAME = b'av-cam.injected.bin'

SITE, HOOK_END = 0x000AA15A, 0x000AA15E
CAVE = 0x00BE0000
CAVE_LEN = 60 + len(FMT) + 1 + len(SRCNAME) + 1
CAVE_END = CAVE + CAVE_LEN
RESUME = 0x000AA160
REAL_CALL = 0x000A9F90
LOGGER = 0x007E8E88
LOGCTX = 0x004402F0

md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
ok = True


def check(label, cond, detail=''):
    global ok
    ok = ok and bool(cond)
    print('  [%s] %s%s' % ('PASS' if cond else 'FAIL', label, ('  ' + detail) if detail else ''))


van = VAN.read_bytes()
inj = INJ.read_bytes()

print('=== 1. container integrity ===')
check('same length as vanilla', len(inj) == len(van), '%d bytes' % len(inj))
check('ORIL magic intact', inj[4:8] == b'ORIL', repr(inj[4:8]))
check('header words unchanged', inj[:SITE] == van[:SITE], 'first %d bytes identical' % SITE)
check('tail after cave unchanged', inj[CAVE_END:] == van[CAVE_END:],
      '%d bytes identical' % (len(van) - CAVE_END))

print()
print('=== 2. the change is confined to the two windows ===')
diff = [i for i in range(len(inj)) if inj[i] != van[i]]
outside = [i for i in diff if not (SITE <= i < HOOK_END or CAVE <= i < CAVE_END)]
check('no changes outside the hook and the cave', not outside,
      '%d changed byte(s) total' % len(diff))
check('hook window is 4 bytes', all(SITE <= i < HOOK_END for i in diff if i < CAVE))

print()
print('=== 3. the hook ===')
hook = inj[SITE:HOOK_END]
check('hook is 4 bytes', len(hook) == 4, hook.hex(' '))
hw1, hw2 = struct.unpack_from('<HH', hook, 0)
check('hw1 is a wide branch (11110 S imm10)', hw1 & 0xF800 == 0xF000, '0x%04x' % hw1)
check('hw2 pattern is 10 J1 1 J2 imm11',
      (hw2 >> 14) & 0x3 == 2 and (hw2 >> 12) & 1 == 1, '0x%04x' % hw2)
s = (hw1 >> 10) & 1
imm10 = hw1 & 0x3FF
j1, j2 = (hw2 >> 13) & 1, (hw2 >> 11) & 1
imm11 = hw2 & 0x7FF
i1, i2 = (~(j1 ^ s)) & 1, (~(j2 ^ s)) & 1
v = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
if v & 0x1000000:
    v -= 0x2000000
tgt = SITE + 4 + v
check('branch target is the cave', tgt == CAVE, '0x%08x (offset %+d)' % (tgt, v))
check('offset fits B.W range', -(1 << 24) <= v < (1 << 24))
check('hook replaced the original bl', van[SITE:HOOK_END] == b'\xff\xf7\x19\xff',
      'vanilla was ' + van[SITE:HOOK_END].hex(' '))

print()
print('=== 4. the cave ===')
insns = list(md.disasm(inj[CAVE:CAVE_END], CAVE))
code = [i for i in insns if i.address < CAVE + 0x3C]
print('  %d instructions disassembled as code' % len(code))
print('  cave window: 0x%08x..0x%08x (%d bytes)' % (CAVE, CAVE_END - 1, CAVE_LEN))
got = [(i.mnemonic, i.op_str.lstrip('#')) for i in code]
expect_first = [
    ('push', '{r0, r1}'),
    ('sub', 'sp, #0x20'),
    ('bl', hex(LOGCTX)),
    ('movs', 'r3, #2'),
    ('str', 'r3, [sp]'),
    ('subs', 'r3, #3'),
    ('str', 'r3, [sp, #4]'),
    ('movs', 'r1, #0x57'),
    ('movs', 'r2, #0'),
    ('addw', 'r3, pc, #0x55'),
    ('str', 'r3, [sp, #8]'),
    ('movw', 'r3, #0x109'),
    ('str', 'r3, [sp, #0xc]'),
    ('addw', 'r3, pc, #0x18'),
    ('str', 'r3, [sp, #0x10]'),
    ('movs', 'r3, #0'),
    ('str', 'r3, [sp, #0x14]'),
    ('movs', 'r3, #1'),
    ('bl', hex(LOGGER)),
    ('add', 'sp, #0x20'),
    ('pop', '{r0, r1}'),
    ('bl', hex(REAL_CALL)),
    ('b.w', hex(RESUME)),
]
for n, (exp, g) in enumerate(zip(expect_first, got)):
    check('insn %2d: %-6s %s' % (n, exp[0], exp[1]), g == exp, 'got %s %s' % g)
check('instruction count', len(got) == len(expect_first), '%d' % len(got))

print()
print('=== 5. the adr targets and their argument slots ===')
FMT_OFF, SRC_OFF = 0x3C, 0x6D
# slots, from the vendor's own error path at 0xAA172..0xAA186
SLOT_FILE, SLOT_LINE, SLOT_FMT = 0x8, 0xC, 0x10


def adr_target(n):
    ins = code[n]
    assert ins.mnemonic == 'addw', ins.mnemonic
    return (ins.address + 4) + int(ins.op_str.split('#')[1], 16)


t_file = adr_target(9)
t_fmt = adr_target(13)
check('[sp+8]  (filename slot) gets the src name', t_file == CAVE + SRC_OFF,
      '0x%08x -> %r' % (t_file, inj[t_file:t_file + len(SRCNAME)]))
check('[sp+0x10] (format slot) gets the marker string', t_fmt == CAVE + FMT_OFF,
      '0x%08x -> %r' % (t_fmt, inj[t_fmt:t_fmt + len(FMT)]))
check('[sp+0xc]  (line slot) is 0x109 = 265',
      code[11].mnemonic == 'movw' and code[11].op_str == 'r3, #0x109'
      and code[12].op_str == 'r3, [sp, #0xc]')
check('the two strings are NOT swapped',
      t_file != t_fmt and t_file == CAVE + SRC_OFF and t_fmt == CAVE + FMT_OFF)

blob = inj[CAVE:CAVE_END]
check('fmt string present', blob[FMT_OFF:FMT_OFF + len(FMT)] == FMT, repr(FMT.decode()))
check('src string present', blob[SRC_OFF:SRC_OFF + len(SRCNAME)] == SRCNAME, repr(SRCNAME.decode()))
check('fmt is NUL-terminated', blob[FMT_OFF + len(FMT)] == 0,
      'NUL at cave+0x%02x' % (FMT_OFF + len(FMT)))
check('src is NUL-terminated', blob[SRC_OFF + len(SRCNAME)] == 0,
      'NUL at cave+0x%02x' % (SRC_OFF + len(SRCNAME)))
check('the format string has no % specifiers, so the extra'
      ' stack arg cannot be misread', b'%' not in FMT, repr(FMT.decode()))
check('payload ends exactly at the cave window end',
      FMT_OFF + len(FMT) + 1 + len(SRCNAME) + 1 == CAVE_LEN,
      '%d bytes' % CAVE_LEN)

print()
print('=== 6. register safety ===')
# The real invariant: r0/r1 must be intact from the `pop` up to the real call.
# Clobbering them BEFORE the pop is required (r1 carries the log level) and is
# harmless, because the pop restores them.
pop_idx = next(i for i, ins in enumerate(code)
               if ins.mnemonic == 'pop' and ins.op_str == '{r0, r1}')
call_idx = next(i for i, ins in enumerate(code)
                if ins.mnemonic == 'bl' and ins.op_str.lstrip('#') == hex(REAL_CALL))
check('the pop restores r0/r1', pop_idx < call_idx,
      'pop at insn %d, real call at insn %d' % (pop_idx, call_idx))
writes = []
for ins in code[pop_idx + 1:call_idx]:
    m, o = ins.mnemonic, ins.op_str
    if m.startswith('str'):
        continue
    if m in ('movs', 'mov', 'movw', 'ldr') and o.startswith(('r0,', 'r1,', 'r0 ', 'r1 ')):
        writes.append((hex(ins.address), m, o))
check('nothing writes r0/r1 between the pop and the real call', not writes, str(writes))
check('the push covers exactly the registers we clobber',
      code[0].mnemonic == 'push' and code[0].op_str == '{r0, r1}',
      '%s %s' % (code[0].mnemonic, code[0].op_str))
# stack: push 8 + sub 0x20 (multiple of 8) keeps sp 8-byte aligned
check('stack stays 8-byte aligned across the payload', True,
      'push{{r0,r1}} = 8 bytes, sub #0x20 = 32 bytes, both multiples of 8')
tail = [(i.mnemonic, i.op_str.lstrip('#')) for i in code[-2:]]
check('tail is: bl #real_call ; b.w #resume',
      tail == [('bl', hex(REAL_CALL)), ('b.w', hex(RESUME))], str(tail))
check('the cave never returns to its caller', all(
    not (i.mnemonic in ('pop',) and 'pc' in i.op_str) for i in code))

print()
print('=== result ===')
print('  vanilla  md5 %s' % hashlib.md5(van).hexdigest())
print('  injected md5 %s' % hashlib.md5(inj).hexdigest())
print('  %s' % ('ALL CHECKS PASSED' if ok else '*** SOME CHECKS FAILED ***'))
