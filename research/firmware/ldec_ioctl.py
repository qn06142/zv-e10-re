"""Follow the ldec ioctl dispatcher to the command that sets the surface.

At VA 0x828B2000 (PA 0x028B2000) there is a driver ioctl handler:

    ldr   r7, [r6, #0x34]      ; driver private data
    add.w r1, r7, #0x1340
    blx   #0x8287A2B0           ; lock
    ldr.w r3, [r8, #0x28]       ; command code from the ioctl argument struct
    cmp   r3, #3
    beq.w #0x828B214A           ; <- command 3

So commands are dispatched by an integer at offset 0x28 of the argument struct.
Command 3 is the branch worth following: on a display driver, "set the source
buffer for scanout" is exactly the kind of command that carries an address.

Method: disassemble from 0x828B214A within the 256 KB already pulled, and look
for the argument being stored into the driver state or handed to the DMA
engine.  We need no further camera round-trips for this.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from thumb import mkdis, dis1, calls_of                                    # noqa: E402
from capstone.arm import ARM_OP_MEM, ARM_OP_IMM, ARM_OP_REG                  # noqa: E402

DESC = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\desc.bin').read_bytes()
BASE_VA = 0x828B2000
md = mkdis()

# ioctl arg fields referenced so far, and the offsets of interest
print('=== the dispatcher, annotated ===')
print('  0x828B2000  ldr   r7, [r6, #0x34]     ; driver priv')
print('  0x828B202C  ldr.w r3, [r8, #0x28]     ; cmd = arg->0x28')
print('  0x828B2030  cmp   r3, #3')
print('  0x828B2032  beq.w 0x828B214A          ; command 3')
print()


def show(va, n=70, label=''):
    off = va - BASE_VA
    print('--- %s  VA 0x%08x (desc.bin + 0x%x) ---' % (label, va, off))
    if off < 0 or off >= len(DESC):
        print('   outside the 256 KB pulled\n')
        return
    a = off
    vcur = va
    cnt = 0
    while cnt < n and a + 4 <= len(DESC):
        i = dis1(md, DESC[a:a + 4], vcur)
        if i is None:
            a += 2
            vcur += 2
            continue
        note = ''
        for op in i.operands:
            if op.type == ARM_OP_MEM and op.mem.disp in (0x28, 0x2C, 0x30, 0x34, 0x38):
                note = '   ; <-- arg offset 0x%x' % op.mem.disp
            if op.type == ARM_OP_IMM and op.imm in (1, 2, 3, 4):
                note = '   ; small int %d' % op.imm
        print('  0x%08x  %-12s %-9s %-30s%s' % (vcur, i.bytes.hex(' '), i.mnemonic,
                                                i.op_str[:30], note))
        a += i.size
        vcur += i.size
        cnt += 1
    print()


show(0x828B214A, 80, 'command 3 handler')

# What other command compares exist in this driver?  Scan the pulled 256 KB for
# `cmp rX, #imm` where X is the register loaded from an argument, to map the
# command set.
print('=== all immediate compares in the first 4 KB (command dispatch table) ===')
a = 0
vcur = BASE_VA
cmps = []
while a < 0x1000 and a + 4 <= len(DESC):
    i = dis1(md, DESC[a:a + 4], vcur)
    if i is None:
        a += 2
        vcur += 2
        continue
    if i.mnemonic == 'cmp' and '#' in i.op_str:
        try:
            imm = int(i.op_str.split('#')[1], 0)
            if 0 <= imm < 64:
                cmps.append((vcur, i.op_str))
        except ValueError:
            pass
    a += i.size
    vcur += i.size
for va, ops in cmps:
    print('   0x%08x  cmp %s' % (va, ops))
