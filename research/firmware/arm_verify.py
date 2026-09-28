"""Verify a hand-built helper ELF before it goes anywhere near the camera.

Two lessons are baked in here, both learned the hard way:

  * capstone prints immediates in whichever base it likes -- `mov r1, #0x10`
    for 16, `mov r7, #0xc0` for 192 -- so immediates must be parsed with
    int(x, 0), never compared against a decimal string.
  * a register can be loaded from several places (the device path and the
    output path both go in r0), so every movw/movt pair must be collected as
    a reconstructed value, not just the last one seen.

Usage: arm_verify.py h_ok.bin | h_dump.bin | h_poke.bin
"""
import struct
import sys
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

HDR, STR_OFF, CODE_OFF, VADDR = 0x54, 0x54, 0x200, 0x00010000
IMG_DIR = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera')

ok = True


def chk(label, cond, detail=''):
    global ok
    ok = ok and bool(cond)
    print('  [%s] %-40s %s' % ('PASS' if cond else 'FAIL', label, detail))


def num(s):
    """Parse a capstone immediate in either base (capstone keeps the '#')."""
    return int(s.strip().lstrip('#'), 0)


def main(name):
    global ok
    img = (IMG_DIR / name).read_bytes()
    (etype, emach, ever, entry, phoff, shoff, flags, ehsz, phsz, phnum,
     shsz, shnum, shstr) = struct.unpack_from('<HHIIIIIHHHHHH', img, 16)
    (pt, poff, pv, pp, pfsz, pmsz, pf, pa) = struct.unpack_from('<IIIIIIII', img, 52)

    print('=== %s  (%d B) ===' % (name, len(img)))
    chk('ELF magic', img[:4] == b'\x7fELF', img[:4].hex(' '))
    chk('class/data/version', (img[4], img[5], img[6]) == (1, 1, 1))
    chk('ET_EXEC + EM_ARM', (etype, emach) == (2, 40),
        'type=%d machine=%d' % (etype, emach))
    chk('EABI5 flags', flags == 0x05000000, '0x%08x' % flags)
    chk('single PT_LOAD', (pt, phnum) == (1, 1))
    chk('p_offset = p_vaddr (mod page)', poff % pa == pv % pa,
        '0x%08x vs 0x%08x mod 0x%x' % (poff, pv, pa))
    chk('p_filesz == bytes after p_offset', pfsz == len(img) - poff,
        'filesz=%d, file=%d' % (pfsz, len(img)))
    chk('p_memsz == p_filesz', pfsz == pmsz)
    chk('entry == vaddr(CODE_OFF)', entry == VADDR + CODE_OFF, '0x%08x' % entry)

    md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
    ins = list(md.disasm(img[CODE_OFF:CODE_OFF + 512], entry))
    chk('entry decodes as ARM', len(ins) >= 6, '%d instructions' % len(ins))

    # every value materialised by a movw/movt pair, per register
    vals = {}
    pend = {}
    for i in ins:
        if i.mnemonic not in ('movw', 'movt'):
            continue
        reg, imm_s = [x.strip() for x in i.op_str.split(',', 1)]
        lo, hi = pend.get(reg, (None, None))
        if i.mnemonic == 'movw':
            lo = num(imm_s)
        else:
            hi = num(imm_s)
        pend[reg] = (lo, hi)
        if lo is not None and hi is not None:
            vals.setdefault(reg, []).append((hi << 16) | lo)

    def has(reg, value):
        return value in vals.get(reg, [])

    def sets_r7(n):
        return any(i.mnemonic == 'mov' and i.op_str == 'r7, #%d' % n for i in ins) \
            or any(i.mnemonic == 'mov' and num(i.op_str.split('#')[1]) == n
                   for i in ins if i.mnemonic == 'mov' and '#' in i.op_str
                   and 'r7' in i.op_str.split(',')[0])

    strings = img[STR_OFF:STR_OFF + 64]
    if b'ZV-E10 helper' in strings:
        mode = 'ok'
    elif b'/dev/stream\x00' in strings:
        mode = 'poke' if any(i.mnemonic == 'strb' for i in ins) else 'dump'
    else:
        mode = 'unknown'
    print('  mode: %s' % mode)

    if mode == 'ok':
        chk('write syscall (r7 = 4)', sets_r7(4))
        chk('string address in r1', has('r1', VADDR + STR_OFF),
            'r1 %s' % [hex(v) for v in vals.get('r1', [])])
    elif mode in ('dump', 'poke'):
        chk('open syscall (r7 = 5)', sets_r7(5))
        chk('mmap2 syscall (r7 = 192)', sets_r7(192))
        chk('exit syscall (r7 = 1)', sets_r7(1))
        dev = img.index(b'/dev/stream\x00')
        chk('dev path address materialised', has('r0', VADDR + dev),
            'r0 %s' % [hex(v) for v in vals.get('r0', [])])
        chk('mmap error bound 0x80000000', has('r1', 0x80000000),
            'r1 %s' % [hex(v) for v in vals.get('r1', [])])
        if mode == 'dump':
            # The page offset and length now come from /setting/parm.bin, so
            # they are loaded with `ldr rX, [sp]` rather than materialised as
            # constants -- there is deliberately no constant in r5 here.
            chk('page offset loaded from parm.bin',
                any(i.mnemonic == 'ldr' and i.op_str.startswith('r5, [sp')
                    for i in ins))
            chk('length loaded from parm.bin',
                any(i.mnemonic == 'ldr' and i.op_str.startswith('r1, [sp')
                    for i in ins))
            chk('reads parm.bin (r7 = 3)',
                any(i.mnemonic == 'mov' and num(i.op_str.split('#')[1]) == 3
                    for i in ins if i.mnemonic == 'mov' and '#' in i.op_str
                    and i.op_str.split(',')[0] == 'r7'))
        else:
            r5 = vals.get('r5', [])
            chk('mmap page offset in r5', bool(r5), 'r5 %s' % [hex(v) for v in r5])
        if mode == 'dump':
            chk('write syscall (r7 = 4)', sets_r7(4))
            out = img.index(b'/setting')
            chk('output path address materialised',
                any(has(r, VADDR + out) for r in vals),
                'r0 %s' % [hex(v) for v in vals.get('r0', [])])
        else:
            chk('fills via strb + loop', any(i.mnemonic == 'strb' for i in ins)
                and any(i.mnemonic == 'bne' for i in ins))
    else:
        chk('mode detected', False, 'unrecognised strings %r' % strings[:32])

    print('  strings: %r' % strings.split(b'\x00\x00')[0])
    return ok


if __name__ == '__main__':
    for n in (sys.argv[1:] or ['h_ok.bin', 'h_dump.bin']):
        main(n)
        print()
    print('=== %s ===' % ('ALL CHECKS PASS' if ok else 'CHECKS FAILED'))
    sys.exit(0 if ok else 1)
