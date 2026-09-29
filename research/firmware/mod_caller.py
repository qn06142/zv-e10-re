"""Examine the single caller of the patched function, to settle whether the
return value 0 or 1 means success or failure - i.e. whether the patch forces
an error or forces success.
"""
import re
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

N = 17_289_388
a = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
FUNC = 0x000aa14c
CALLER = 0x000a4338
PATCH = 0x000aa15a

md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)

print('=== find the enclosing function of the call site 0x%06x ===' % CALLER)
start = None
for i in range(CALLER, CALLER - 0x400, -2):
    hw1 = struct.unpack_from('<H', a, i)[0]
    # PUSH.W / PUSH with lr  (0xE92D / 0xB5xx with bit7 set)
    if (hw1 & 0xFF00) == 0xB500 and (hw1 & 0x80):
        start = i
        break
    if hw1 == 0xE92D or (hw1 & 0xFE00) == 0xE800:
        start = i
        break
print('  prologue candidate at 0x%06x' % (start if start else 0))
lo = start if start else CALLER - 0x80
print()
print('=== the caller, from 0x%06x, around the call ===' % lo)
for ins in md.disasm(a[lo:CALLER + 0x60], lo):
    mark = ''
    if ins.address == CALLER:
        mark = '   <<<< calls the patched function'
    if ins.address == CALLER - 4:
        mark = '   <<< argument setup'
    print('  0x%08x  %-12s %-40s%s' % (ins.address, ins.bytes.hex(' '),
                                       ins.mnemonic + ' ' + ins.op_str, mark))
print()

print('=== which source file does THIS function log from? ===')
# look for a pc-relative string load + a filename string in the function body
body = a[lo:CALLER + 0x200]
for m in re.finditer(rb'[\x20-\x7e]{6,120}', a[lo:CALLER + 0x400]):
    s = m.group().decode('ascii')
    if re.fullmatch(r'[\w./+-]+\.(?:cpp|c|h|hpp|cc)', s):
        print('  0x%08x  %s' % (lo + m.start(), s))
print()

print('=== summary of the patched function ===')
print('  0x%06x  push {r4,lr}                      <- function entry' % FUNC)
print('  0x%06x  ldr  r0,[r0]; bl 0x6aa366' % (FUNC + 6))
print('  0x%06x  mov  r1,r4' % (FUNC + 12))
print('  0x%06x  bl   #0xa9f90                     <- REMOVED by the mod' % PATCH)
print('  0x%06x  cmp  r0,#1 ; bls +0x30            <- r0<=1 => "return 1"' % (PATCH + 4))
print('  0x%06x  bl   #0x4402f0                    <- error handler' % (PATCH + 10))
print('            log W "Err!:result:%%x" (dec/sfmc_dec_input_i.cpp:265)')
print('            movs r0,#0 ; return 0')
print()
print('  with the mod: r0 := 0x850 always => always takes the error branch')
