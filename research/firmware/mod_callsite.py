"""Tight window around the single call site 0xa4338."""
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

a = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
CALLER = 0x000a4338
FUNC = 0x000aa14c
PATCH = 0x000aa15a
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)

print('=== 0x%06x .. 0x%06x  (the call site and how r0 is consumed) ===' % (CALLER - 0x30, CALLER + 0x40))
for ins in md.disasm(a[CALLER - 0x30:CALLER + 0x40], CALLER - 0x30):
    mark = ''
    if ins.address == CALLER:
        mark = '   <<<< calls patched fn 0xaa14c'
    print('  0x%08x  %-12s %-38s%s' % (ins.address, ins.bytes.hex(' '),
                                       ins.mnemonic + ' ' + ins.op_str, mark))
print()

# the case label that jumps to this block, if any
print('=== the case value that dispatches here ===')
# scan backwards for a 'b' whose target is this block
for i in range(CALLER - 0x4, 0xa417a, -2):
    hw = struct.unpack_from('<H', a, i)[0]
    if (hw & 0xF800) == 0xE000:      # B T2
        s = (hw >> 10) & 1
        imm10 = hw & 0x3FF
        j1 = (struct.unpack_from('<H', a, i + 2)[0] >> 13) & 1
        j2 = (struct.unpack_from('<H', a, i + 2)[0] >> 11) & 1
        imm11 = struct.unpack_from('<H', a, i + 2)[0] & 0x7FF
        i1 = (~(j1 ^ s)) & 1
        i2 = (~(j2 ^ s)) & 1
        v = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
        if v & 0x1000000:
            v -= 0x2000000
        tgt = i + 4 + v
        if tgt == CALLER - 0x30 or (tgt <= CALLER <= tgt + 0x20):
            print('  branch at 0x%06x -> 0x%06x (enters this block)' % (i, tgt))
            # walk back for the cmp/movw that set the case value
            for j in range(i, max(0xa417a, i - 0x40), -2):
                w2 = struct.unpack_from('<H', a, j)[0]
                if (w2 & 0xFBF0) == 0xF240:   # MOVW
                    imm = ((w2 & 0xF) << 12) | (((struct.unpack_from('<H', a, j + 2)[0] >> 10) & 1) << 11) \
                          | (((struct.unpack_from('<H', a, j + 2)[0] >> 13) & 1) << 8) \
                          | (struct.unpack_from('<H', a, j + 2)[0] & 0xFF)
                    print('      movw r%d, #0x%x   <-- case ID' % (w2 & 0xF, imm))
            break
print()
print('=== PATCHED FUNCTION recap ===')
print('  entry  0x%06x' % FUNC)
print('  call   0x%06x  bl #0xa9f90     -> removed by the mod' % PATCH)
print('  test   0x%06x  cmp r0,#1 / bls  -> r0<=1 : "ok", r0>1 : error' % (PATCH + 4))
print('  error  logs W "Err!:result:%%x" from dec/sfmc_dec_input_i.cpp:265, returns 0')
print('  mod    r0 := 0x850 (2128) always  -> always the error branch')
