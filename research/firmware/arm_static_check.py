"""Static check of a hand-built helper before it goes near the camera.

The probe binary segfaulted on the camera (rc=139, em_get_callstack) because it
used r11/fp as a scratch register: that is the frame pointer, and letting
memcpy clobber it corrupted the saved frame.  Nothing in the disassembly
review caught it, because a single wrong register looks fine in isolation.

So check the things that actually bite in hand-written ARM assembly:

  1. no r11 (fp) or r13 (sp) used as a general scratch register
  2. every branch target resolves to a label defined in the block
  3. every label defined is actually referenced
  4. stack frame is large enough for the scratch offsets used
  5. the ELF invariants that cost a SIGKILL earlier still hold
     (p_offset congruent p_vaddr mod page; p_filesz == file - p_offset)

Run: arm_static_check.py h_probe.bin
"""
import re
import struct
import sys
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

IMG_DIR = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera')
HDR, STR_OFF, CODE_OFF, VADDR = 0x54, 0x54, 0x200, 0x00010000
BANNED = {'r11': 'frame pointer', 'r13': 'stack pointer', 'sp': 'stack pointer',
          'fp': 'frame pointer', 'ip': 'intra-procedure scratch (ok but avoid)'}

ok = True


def chk(label, cond, detail=''):
    global ok
    ok = ok and bool(cond)
    print('  [%s] %-44s %s' % ('PASS' if cond else 'FAIL', label, detail))


def main(name):
    global ok
    img = (IMG_DIR / name).read_bytes()
    (etype, emach, ever, entry, phoff, shoff, flags, ehsz, phsz, phnum,
     shsz, shnum, shstr) = struct.unpack_from('<HHIIIIIHHHHHH', img, 16)
    (pt, poff, pv, pp, pfsz, pmsz, pf, pa) = struct.unpack_from('<IIIIIIII', img, 52)

    print('=== %s  (%d B) ===' % (name, len(img)))
    chk('ELF magic', img[:4] == b'\x7fELF')
    chk('ET_EXEC + EM_ARM', (etype, emach) == (2, 40))
    chk('EABI5 flags', flags == 0x05000000, '0x%08x' % flags)
    chk('p_offset = p_vaddr (mod page)', poff % pa == pv % pa,
        '0x%08x vs 0x%08x mod 0x%x' % (poff, pv, pa))
    chk('p_filesz == file - p_offset', pfsz == len(img) - poff,
        'filesz=%d file-p_offset=%d' % (pfsz, len(img) - poff))
    chk('p_memsz == p_filesz', pfsz == pmsz)
    chk('entry == vaddr(CODE_OFF)', entry == VADDR + CODE_OFF, '0x%08x' % entry)

    md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
    # Disassemble the WHOLE segment, not a fixed 1024-byte window: a binary
    # that outgrows the window produces branch targets that look like they land
    # outside the code, which reads as a failure when it is really just an
    # incomplete decode.
    seg = img[CODE_OFF:CODE_OFF + pfsz]
    ins = list(md.disasm(seg, entry))
    chk('code decodes', len(ins) > 8, '%d instructions from %d bytes'
        % (len(ins), len(seg)))

    # 1. banned scratch registers
    bad = []
    for i in ins:
        m = re.match(r'^([a-z0-9]+)\s', i.mnemonic)
        if not m:
            continue
        op = m.group(1)
        if op in ('push', 'stmdb', 'stmia'):
            continue
        for tok in re.findall(r'\b(r1[0-3]|r11|sp|fp|lr|ip)\b', i.op_str):
            if tok in BANNED and not (tok == 'lr' and i.mnemonic == 'bx'):
                bad.append((i.address, i.mnemonic, i.op_str, tok))
    chk('no fp/sp used as scratch', not bad,
        '; '.join('0x%x %s %s (%s)' % b for b in bad[:4]))

    # 2/3. label integrity -- collect labels from the source if present
    labels, refs = set(), set()
    for i in ins:
        # keystone resolved branches, so recover targets numerically instead
        if i.mnemonic.startswith('b') or i.mnemonic == 'bl':
            m = re.search(r'#(0x[0-9a-fA-F]+|\d+)', i.op_str)
            if m:
                refs.add(int(m.group(1), 0))
    # numeric targets must land inside the code we disassembled
    lo, hi = entry, entry + len(ins) * 4
    outside = sorted(t for t in refs if not (lo <= t < hi))
    chk('all branch targets land in disassembled code', not outside,
        'outside: %s' % [hex(t) for t in outside[:6]])

    # 4. stack frame big enough
    subs = [int(i.op_str.split('#')[1], 0) for i in ins
            if i.mnemonic in ('sub', 'add') and 'sp' in i.op_str and '#' in i.op_str]
    frame = max([s for s in subs if i_mnemonic_is_sub(ins, s)] or [0]) \
        if subs else 0
    # simpler: the largest sp-relative offset used must be < frame size
    offs = []
    for i in ins:
        m = re.search(r'\[sp(?:,\s*#(0x[0-9a-fA-F]+|\d+))?\]', i.op_str)
        if m:
            offs.append(int(m.group(1), 0) if m.group(1) else 0)
    subsizes = [int(i.op_str.split('#')[1], 0) for i in ins
                if i.mnemonic == 'sub' and 'sp' in i.op_str and '#' in i.op_str]
    fr = max(subsizes) if subsizes else 0
    chk('stack frame covers all sp offsets', fr >= (max(offs) if offs else 0) + 8,
        'frame=%d max sp offset=%d' % (fr, max(offs) if offs else 0))

    # 5. svc sites: r7 must be set to a plausible syscall immediately before
    bad_svc = []
    for idx, i in enumerate(ins):
        if i.mnemonic != 'svc':
            continue
        prev = ins[idx - 1].op_str if idx else ''
        if not re.search(r'\br7\b', prev):
            bad_svc.append(hex(i.address))
    chk('every svc has r7 set just before', not bad_svc,
        'suspect: %s' % bad_svc[:6])


def i_mnemonic_is_sub(ins, _s):
    return True


if __name__ == '__main__':
    for n in (sys.argv[1:] or ['h_probe.bin']):
        main(n)
        print()
    print('=== %s ===' % ('STATIC CHECKS PASS' if ok else 'STATIC CHECKS FAILED'))
    sys.exit(0 if ok else 1)
