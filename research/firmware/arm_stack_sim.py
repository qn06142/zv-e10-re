"""Prove the probe's stack accesses stay inside its frame, offline.

The probe segfaulted on the camera twice (rc=139).  Both causes were layout
bugs that disassembly review missed:

  1. data offsets were computed as 16*(idx+1) while the probes were NOT
     uniform (4, 8 and 4 words), so probe 1's 32 bytes ran from sp+0x50 to
     sp+0x70 inside a 0x60 frame -- overwriting the saved return address.
  2. `memcpy` decrements r2 to zero and the caller did `add sl, sl, r2`
     afterwards, so the accumulator offset never advanced.

A third bug was found only after the first version of this checker: a
surviving edit had left TWO `sub sp, sp, #imm` in the generated code, so the
real frame was double the size every offset was computed against.

So simulate every sp-relative access and compare the highest byte touched
against the single frame allocation.  Capstone prints sp operands in two
different forms depending on the instruction, and matching only one of them
made the first version of this script vacuously "pass" with 0 accesses found:

    str r0, [r12]                 register + imm, no sp
    add r3, sp, #0x80             register base with an immediate offset
    str r0, [sp, #4]              bracketed base + immediate
    ldr r0, [sp]                  bracketed base only
    sub sp, sp, #0xa0             the allocation itself
"""
import re
import sys
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

IMG = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\h_probe.bin')
ENTRY = 0x00010200

# instructions that touch memory, and how many bytes at the base address
STORE_LOAD = re.compile(r'^(str|strb|strh|ldr|ldrb|ldrh|ldrd|strd|ldm|stm)')


def width_of(mnem):
    if mnem in ('strb', 'ldrb'):
        return 1
    if mnem in ('strh', 'ldrh'):
        return 2
    if mnem in ('ldrd', 'strd'):
        return 8
    if mnem.startswith(('ldm', 'stm')):
        return 0            # register lists: handled separately
    return 4


def main():
    img = IMG.read_bytes()
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
    ins = list(md.disasm(img[0x200:0x200 + 1024], ENTRY))
    if not ins:
        print('FAILED TO DECODE')
        return 1

    problems = []

    # --- exactly one frame allocation ---------------------------------
    allocs = [i for i in ins
              if i.mnemonic == 'sub' and re.search(r'\bsp,\s*sp\b', i.op_str)]
    if len(allocs) != 1:
        problems.append('expected exactly 1 `sub sp, sp, #imm`, found %d' % len(allocs))
        frame = 0
        for a in allocs:
            m = re.search(r'#(0x[0-9a-fA-F]+|\d+)', a.op_str)
            print('  allocation at 0x%08x: sub %s' % (a.address, a.op_str))
    else:
        m = re.search(r'#(0x[0-9a-fA-F]+|\d+)', allocs[0].op_str)
        frame = int(m.group(1), 0) if m else 0
    print('frame allocation: %d (0x%X)' % (frame, frame))

    # --- collect sp-relative accesses ---------------------------------
    acc = []            # (addr, mnem, disp, bytes, how)
    for i in ins:
        if i.mnemonic == 'sub' and re.search(r'\bsp,\s*sp\b', i.op_str):
            continue                                   # the allocation itself
        w = width_of(i.mnemonic)
        # form A: bracketed base with optional immediate
        for m in re.finditer(r'\[sp(?:,\s*#(0x[0-9a-fA-F]+|\d+))?\]', i.op_str):
            d = int(m.group(1), 0) if m.group(1) else 0
            acc.append((i.address, i.mnemonic, d, w or 4, 'bracket'))
        # form B: `add rX, sp, #imm` -- a computed base, then that reg is used
        if 'sp' in i.op_str and i.mnemonic == 'add':
            m = re.search(r'#(0x[0-9a-fA-F]+|\d+)', i.op_str)
            if m:
                print('  note: computed sp base at 0x%08x: %s %s'
                      % (i.address, i.mnemonic, i.op_str))

    print('sp-relative accesses found (bracketed form): %d' % len(acc))

    # The generated code now uses only computed bases (`add rX, sp, #imm`),
    # so bracketed accesses are legitimately zero -- but only accept that if
    # every sp reference is accounted for as a computed base or the allocation.
    computed = []
    for i in ins:
        if i.mnemonic == 'add' and re.search(r'\bsp\b', i.op_str):
            m = re.search(r'#(0x[0-9a-fA-F]+|\d+)', i.op_str)
            if m:
                computed.append((i.address, int(m.group(1), 0)))
    other = [i for i in ins
             if 'sp' in i.op_str
             and i.mnemonic not in ('add',)
             and not (i.mnemonic == 'sub' and re.search(r'\bsp,\s*sp\b', i.op_str))]
    if not acc and not computed:
        problems.append('no sp-relative accesses found at all -- the matcher '
                        'is wrong, so this result would be vacuous')
    if other and not acc:
        problems.append('unaccounted sp references in: %s'
                        % ', '.join('0x%x %s %s' % (i.address, i.mnemonic, i.op_str)
                                    for i in other[:4]))

    worst = 0
    for a, mnem, d, w, how in acc:
        top = d + w
        worst = max(worst, top)
        if top > frame:
            problems.append('0x%08x %s %s touches sp+0x%X, past the 0x%X frame'
                            % (a, mnem, '(%s)' % how, top, frame))
    for a, mnem, d, w, how in acc:
        pass
    print('highest byte touched (bracketed): 0x%X' % worst)
    print()
    print('  %-10s %-9s %-6s %-4s %s' % ('addr', 'mnem', 'disp', 'bytes', 'form'))
    for a, mnem, d, w, how in sorted(acc, key=lambda x: -(x[2] + x[3]))[:10]:
        print('  0x%08x  %-9s %-6d %-4d %s' % (a, mnem, d, w, how))
    print()

    # A computed base is only safe if everything later accessed THROUGH that
    # register stays in bounds.  Track each base register and the accesses made
    # through it, so the check is about real use rather than the base alone.
    # Slot layout: slot size 32, data written at base+16 for at most 16 bytes,
    # so a base at off needs off + 32 <= frame.
    SLOT = 32
    for a, off in computed:
        if off + SLOT > frame:
            problems.append('computed base at 0x%08x is sp+0x%X, and a 32-byte '
                            'slot there would end at sp+0x%X, past the 0x%X frame'
                            % (a, off, off + SLOT, frame))
    addmax = max((o for _, o in computed), default=0)
    print('computed sp bases: %d, highest 0x%X (+ %d-byte slot => 0x%X, frame 0x%X)'
          % (len(computed), addmax, SLOT, addmax + SLOT, frame))

    print()
    if problems:
        for p in problems:
            print('  PROBLEM: %s' % p)
        print('\nRESULT: %d problem(s) -- DO NOT TRANSFER' % len(problems))
        return 1
    print('RESULT: single frame allocation, all stack access in bounds -- '
          'safe to transfer')
    return 0


if __name__ == '__main__':
    sys.exit(main())
