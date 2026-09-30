"""Shared Thumb helpers for the av-cam.bin work.

Centralising these because the same bug bit three separate analyses: an
epilogue test that matched only the bare mnemonic missed the wide encodings,
never stopped, ran past the end of a function, and silently attributed every
following function's instructions and call targets to the function before it.
That produced a fake "calls memcpy twice" signal and a fake 136-instruction
function.  is_return() below matches on the mnemonic *stem* so it is correct
whatever spelling the installed capstone uses -- 5.0.7 normalises the wide form
to `pop`, older builds emit `pop.w`, and a `== 'pop'` test is right on one and
wrong on the other.  See 06-method.md.
"""
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN
from capstone.arm import ARM_OP_REG, ARM_OP_IMM, ARM_OP_MEM

CS_ARCH, CS_MODE = CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN

# capstone's PC register id is 11, not 13 (13 is not a register at all)
PC = 11


def mkdis():
    md = Cs(CS_ARCH, CS_MODE)
    md.detail = True
    return md


def dis1(md, buf, addr):
    """First instruction at addr, padding the buffer.

    capstone refuses to decode a bare 4-byte Thumb-2 word with nothing
    following it, returning nothing instead of the instruction.
    """
    for extra in (b'', b'\x00' * 4, b'\x00' * 8, b'\x00' * 16):
        for i in md.disasm(bytes(buf) + extra, addr):
            return i
    return None


def is_return(ins):
    """True for any pop/bx/ldm* variant that ends a function.

    Two traps this has to avoid:

    1. The epilogue may be spelled `pop`, `pop.w`, `ldmia`, `ldmia.w` or
       `ldmdb`, and which spelling comes out depends on the capstone build --
       5.0.7 reports `pop` for both the narrow and the wide encoding.  A test
       on the bare mnemonic therefore works on one version and misses every
       wide form on another, and the walk then runs off the end of the
       function, attributing the next functions' code to this one.  Hence the
       stem.

    2. `pc` merely APPEARING in the operand string is not a return.  Every
       PC-relative literal load prints as `ldr r3, [pc, #0x10c]`.  So for
       load forms the destination register has to be checked, not the text.
    """
    if ins is None:
        return False
    stem = ins.mnemonic.split('.')[0]
    if stem == 'bx':
        return True
    if stem in ('pop', 'ldm', 'ldmia', 'ldmdb', 'ldmda'):
        return 'pc' in ins.op_str
    if stem == 'ldr':
        # only a jump-to-pc is a return; a [pc,...] source is a literal load
        return ins.op_str.split(',')[0].strip() == 'pc'
    return False


def is_prologue(av, addr):
    if addr + 2 > len(av):
        return False
    hw = struct.unpack_from('<H', av, addr)[0]
    if (hw & 0xFF00) == 0xB500 and (hw & 0x80):      # 16-bit push {..,lr}
        return True
    if hw == 0xE92D or (hw & 0xFF00) == 0xE800:      # 32-bit push.w / stmdb
        return True
    return False


def walk(md, av, start, limit=0x2000, stop_on_return=True):
    """Linear disassembly of one function.  Stops at a real return."""
    out = []
    addr = start
    end_bound = min(start + limit, len(av))
    while addr < end_bound:
        i = dis1(md, av[addr:addr + 4], addr)
        if i is None:
            break
        out.append(i)
        addr += i.size
        if stop_on_return and is_return(i):
            break
    return out


def calls_of(insns):
    out = []
    for i in insns:
        if i.mnemonic.split('.')[0] == 'bl':
            try:
                out.append(int(i.op_str.split('#')[-1], 16))
            except ValueError:
                pass
    return out


def decode_movw(hw1, hw2):
    """MOVW T2 (bits9-4 == 100100) and T3 (bits9-4 == 101000).

    imm16 = imm4:i:imm3:imm8.  imm3 is bits 14-12 of hw2 -- reading bit 13
    instead decodes every large immediate wrongly.
    """
    if (hw1 >> 11) != 0b11110 or (hw2 >> 15):
        return None, None
    if ((hw1 >> 4) & 0x3F) not in (0b100100, 0b101000):
        return None, None
    return (((hw1 & 0xF) << 12) | (((hw1 >> 10) & 1) << 11)
            | (((hw2 >> 12) & 7) << 8) | (hw2 & 0xFF)), (hw2 >> 8) & 0xF


def bl_target(av, i):
    """Immediate BL target at a 32-bit Thumb site, decoded by hand."""
    if i + 4 > len(av):
        return None
    hw1, hw2 = struct.unpack_from('<HH', av, i)
    if hw1 & 0xF800 != 0xF000 or (hw1 & 0xF000) != 0xF000 or (hw1 & 0x0800):
        return None
    s = (hw1 >> 10) & 1
    imm10 = hw1 & 0x3FF
    j1, j2 = (hw2 >> 13) & 1, (hw2 >> 11) & 1
    imm11 = hw2 & 0x7FF
    i1, i2 = (~(j1 ^ s)) & 1, (~(j2 ^ s)) & 1
    v = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
    if v & 0x1000000:
        v -= 0x2000000
    return i + 4 + v


# --- string / data references -------------------------------------------
#
# av-cam.bin is a raw binary, not an ELF, and carries no relocations.  A
# pointer to a string or table is built in two instructions:
#
#     ldr  rX, [pc, #imm]      ; pool word is a FILE offset, not an address
#     add  rX, pc              ; rX = pool + pc  ->  the file offset
#
# Two mistakes in this decoder cost several sessions' worth of false negatives
# (0 of 36 strings resolving), so both are pinned by the self-tests below:
#
#   1. Do NOT apply the load base.  The pool word and `addr` are both file
#      offsets, so their sum is already the target.  Subtracting BASE shifts
#      every key by 6.4 MB and nothing ever matches.
#
#   2. pc is the RAW (addr + 4), NOT Align(PC,4).  ARM's architecture says
#      ADD (register) reads Align(PC,4), but this toolchain's encoded literal
#      is target - (addr+4).  Using the aligned value lands 2 bytes low, which
#      is why the first version needed a +/-2 neighbourhood probe to find
#      anything.  Confirmed independently twice: the signature strings match
#      their regex offsets exactly under the raw convention, and the
#      brightness LUT base comes out 4-byte aligned (as a
#      `ldr.w rX, [rX, rY, lsl #2]` base must be) under raw and 2 mod 4
#      under aligned.

def pcrel_strrefs(md, av, start=0x1000, end=None):
    """Map every pc-relative-referenced FILE OFFSET to the `add ...,pc` sites.

    Returns {file_offset: [add_instruction_addr, ...]}.
    """
    from capstone.arm_const import ARM_REG_R0
    if end is None:
        end = len(av)
    reg = {ARM_REG_R0 + i: i for i in range(13)}
    pend = {}
    out = {}
    for addr in range(start, min(end, len(av)) - 4, 2):
        ins = dis1(md, av[addr:addr + 4], addr)
        if ins is None:
            continue
        ops = ins.operands
        stem = ins.mnemonic.split('.')[0]
        if stem == 'ldr' and len(ops) == 2 and ops[1].type == ARM_OP_MEM \
                and ops[1].mem.base == PC and ops[0].reg in reg:
            pool = ((addr + 4) & ~3) + ops[1].mem.disp
            if 0 <= pool <= len(av) - 4:
                pend[reg[ops[0].reg]] = struct.unpack_from('<I', av, pool)[0]
        elif stem == 'add' and len(ops) == 2 and ops[1].reg == PC \
                and ops[0].reg in reg:
            val = pend.pop(reg[ops[0].reg], None)
            if val is not None:
                t = (val + addr + 4) & 0xFFFFFFFF      # raw PC, no BASE
                if 0 < t < len(av):
                    out.setdefault(t, []).append(addr)
        if len(pend) > 24:                            # lost-sync guard
            pend.clear()
    return out


def strref_at(av, refs, off):
    """The `add ...,pc` instruction referencing file offset `off`, or None."""
    for cand in (off, off & ~1, off & ~3, off - 1, off - 2, off + 2):
        if cand in refs:
            return refs[cand][0]
    return None


def _selftest():
    """Both conventions are pinned by independently-anchored ground truth."""
    from pathlib import Path
    av = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
    md = mkdis()
    refs = pcrel_strrefs(md, av, 0x1000, 0x200000)

    # ground truth 1: the 3-string log macro at 0x001621A8, verified by hand
    #   ldr r0,[pc,#0x180] ; add r0,pc  ->  "[VDF-ABT]%s %s %dcd:0x%x"
    #   ldr r1,[pc,#0x180] ; add r1,pc  ->  "VdfInputCmdReleasePinandMem.cpp"
    #   ldr r2,[pc,#0x184] ; add r2,pc  ->  the Execute() signature string
    # These strings are referenced from MANY sites, so membership, not
    # equality, is the correct assertion -- a single-element list is wrong.
    ok1 = 0x001621b0 in refs.get(0x00986812, ())
    ok1 &= 0x001621b4 in refs.get(0x00987239, ())
    ok1 &= 0x001621b6 in refs.get(0x0098c37e, ())
    # ground truth 2: LUT base used as `ldr.w r3,[r3,r2,lsl #2]` -> 4-aligned
    # under the raw-pc convention and 2 mod 4 under Align(PC,4)
    ok2 = bool(refs.get(0x0087d7e4)) and (0x0087d7e4 % 4 == 0)

    for name, ok in (('log-macro triple', ok1), ('aligned LUT base', ok2)):
        print('%-24s %s' % (name, 'PASS' if ok else 'FAIL'))
    assert ok1 and ok2, 'pcrel_strrefs convention regressed'
    print('pcrel_strrefs: 2/2 PASS  (%d targets in 0x1000..0x200000)' % len(refs))


if __name__ == '__main__':
    _selftest()

