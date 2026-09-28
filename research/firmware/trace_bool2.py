"""Decode only real function bodies. Capstone was desynchronising over data.

The bug that made the last run return zero
-------------------------------------------
Decoding the whole .text with skipdata=True produced 2,908,378 "instructions",
and the mnemonics were full of things that do not exist in ARM:

    ldrtmi   ldreq   ldrtmi   ldrbpl   ldrvs   ldrdeq   ldrlo

Those are capstone sliding past the end of an instruction and reinterpreting
literal-pool data as opcodes.  Once desynchronised, everything downstream is
fiction: the ldrb [#0x11] search found 0 hits, and so did both controls, which
is the tell -- a control that also returns zero means the instrument is broken,
not the target absent.  That is the same lesson as the five data searches, and
it cost one more run.

The fix
-------
Thumb function bodies are contiguous code between a push-with-lr and the matching
pop.  Literal pools sit between functions, not inside them, so decoding
function-by-function keeps the instruction stream aligned.  The function list
comes from disasm_dispatch.py's recovery, which found 48,612 starts with a
median body of 34 bytes -- consistent with a real static library, and therefore
trustworthy enough to decode inside.

Verification before trusting any output
--------------------------------------
A decode is only meaningful if the instruction stream stays aligned.  Three
checks, all cheap:

  A1  Coverage: how many bytes of .text are inside a recovered function, and how
      many instructions decode.  If coverage is a small fraction, the rest is
      pools and the approach is still correct.
  A2  Sanity: the fraction of decoded instructions that are branches, loads,
      stores, ALU and so on, versus anything that looks like a condition-code
      suffix glued onto ldr.  Real Thumb has almost no ldr<cond>; desynchronised
      output is full of them.  Counting them is a direct misalignment detector.
  A3  The control: if a byte-load at a real field offset still returns zero
      after the fix, that is a finding.  If it returns zero again, the
      instrument is still broken.

A2 is the important one.  If ldr<cond> forms drop from tens of thousands to
near zero, the alignment is fixed, and that is measurable rather than asserted.
"""
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

SO = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\engine\viewUnified2.so')
TEXT_OFF = 0x0018eec8
TEXT_SIZE = 0x074af6c
TEXT_END = TEXT_OFF + TEXT_SIZE
BOOL_OFF = 0x11


def find_functions(b, lo, hi, maxsz=0x4000):
    starts = []
    for o in range(lo, hi - 4, 2):
        w = struct.unpack_from('<H', b, o)[0]
        if (w & 0xFF00) == 0xB500 or (w & 0xFE00) == 0xB400:
            if o >= 8:
                starts.append(o)
    starts = sorted(set(starts))
    ends = starts[1:] + [hi]
    out = []
    for s, e in zip(starts, ends):
        if 0 < e - s <= maxsz:
            out.append((s, e))
    return out


def decode_functions(b, funcs):
    """Decode each function separately, keeping the stream aligned."""
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    md.skipdata = False
    all_ins = []
    for s, e in funcs:
        for x in md.disasm(b[s:e], s):
            all_ins.append(x)
    return all_ins


def main():
    b = SO.read_bytes()
    print('=== viewUnified2.so ===')
    print()
    print('A1  coverage')
    funcs = find_functions(b, TEXT_OFF, TEXT_END)
    covered = sum(e - s for s, e in funcs)
    print('  .text size          : %d bytes' % TEXT_SIZE)
    print('  functions recovered : %d' % len(funcs))
    print('  bytes inside one    : %d  (%.1f%% of .text)'
          % (covered, 100.0 * covered / TEXT_SIZE))
    print('  the remainder is literal pools and alignment padding, which is')
    print('  expected and is exactly what must not be decoded as code.')
    print()

    ins = decode_functions(b, funcs)
    print('  instructions decoded: %d' % len(ins))
    print()

    print('A2  alignment sanity: ARM has almost no ldr<cond>')
    print()
    mn = Counter(x.mnemonic for x in ins)
    cond_suffix = sum(c for m, c in mn.items()
                      if re.match(r'^ldr[bhs]?[a-z]{2}$', m) and m not in (
                          'ldrd', 'ldrex', 'ldrexh'))
    clean = sum(c for m, c in mn.items()
                if m in ('ldr', 'ldrb', 'ldrh', 'ldrsb', 'ldrsh', 'str',
                         'strb', 'strh', 'ldm', 'stm', 'push', 'pop', 'b',
                         'bl', 'blx', 'bx', 'cbz', 'cbnz', 'mov', 'movs',
                         'add', 'adds', 'sub', 'subs', 'cmp', 'and', 'orr',
                         'eor', 'lsl', 'lsr', 'asr', 'ror', 'mul', 'mvn',
                         'tst', 'adr', 'nop', 'uxtb', 'uxth', 'sxtb', 'sxth',
                         'lsls', 'asrs', 'lsl.w', 'asr.w', 'pop.w', 'push.w',
                         'add.w', 'sub.w', 'movw', 'movt', 'it', 'ite',
                         'cbz.w', 'cbnz.w', 'tst.w', 'cmp.w', 'and.w',
                         'orr.w', 'bic.w', 'lsl.w', 'rsb.w', 'mvn.w',
                         'uxtb.w', 'uxth.w', 'adds.w', 'subs.w', 'str.w',
                         'ldr.w', 'orr.w', 'lsl.w', 'ubfx', 'ubf.w', 'sxtab'))
    total = sum(mn.values())
    print('  total instructions          : %d' % total)
    print('  ldr/str with a condition suffix: %d  (%.2f%%)'
          % (cond_suffix, 100.0 * cond_suffix / max(1, total)))
    print('  recognised real Thumb forms  : %d  (%.1f%%)'
          % (clean, 100.0 * clean / max(1, total)))
    print()
    if cond_suffix / max(1, total) < 0.01:
        print('  >> alignment holds: ldr<cond> is rare, so the stream is aligned.')
        print('     The previous run, which had tens of thousands, was not.')
    else:
        print('  >> still misaligned. Do not trust any filter built on this.')
    print()
    print('  most common mnemonics: %s'
          % ', '.join('%s:%d' % (m, c) for m, c in mn.most_common(16)))
    print()

    # A3: the search that previously returned zero for everything
    print('A3  re-run the search that previously found nothing')
    print()
    for want in (BOOL_OFF, 0x10, 0x12):
        hits = []
        for x in ins:
            if not x.mnemonic.startswith('ldrb'):
                continue
            if ('#%d]' % want) in x.op_str or ('#0x%x]' % want) in x.op_str:
                hits.append(x)
        print('  ldrb [rN, #0x%02x] : %d' % (want, len(hits)))
    print()
    print('  if 0x11 now differs from the controls, the instrument works and')
    print('  the difference is a finding.  if all three are equal, it is not.')
    print()

    # now the real analysis: loads at 0x11 whose value is then used
    print('=' * 76)
    print('consumers of the boolean field at +0x11')
    print('=' * 76)
    byaddr = {x.address: i for i, x in enumerate(ins)}
    hits = []
    for i, x in enumerate(ins):
        if not x.mnemonic.startswith('ldrb'):
            continue
        if ('#0x11]' not in x.op_str) and ('#17]' not in x.op_str):
            continue
        reg = x.op_str.split(',')[0].strip()
        acts = []
        for y in ins[i + 1:i + 12]:
            if reg not in y.op_str and y.mnemonic not in ('cbz', 'cbnz'):
                continue
            if y.mnemonic.startswith('b') or y.mnemonic in ('cbz', 'cbnz'):
                acts.append('BRANCH %s %s' % (y.mnemonic, y.op_str))
            elif y.mnemonic in ('and', 'orr', 'bic', 'eor', 'tst', 'mvn',
                                'lsl', 'lsr', 'asr', 'uxtb', 'uxth', 'cmp',
                                'cmn', 'subs', 'adds', 'ror'):
                acts.append('USE %s %s' % (y.mnemonic, y.op_str))
        if acts:
            hits.append((x, acts))
    print('  %d loads whose value is branched on or manipulated' % len(hits))
    print()
    for x, acts in hits[:30]:
        print('  0x%08x  %-6s %-22s  %s'
              % (x.address, x.mnemonic, x.op_str, '; '.join(acts[:2])))
    print()
    if hits:
        print('  --- full context of the first 5 ---')
        for x, acts in hits[:5]:
            print()
            print('  0x%08x' % x.address)
            i = byaddr[x.address]
            for y in ins[max(0, i - 8):i + 14]:
                mk = '   <<< boolean field' if y.address == x.address else ''
                print('    %08x  %-8s %-26s%s'
                      % (y.address, y.mnemonic, y.op_str, mk))


if __name__ == '__main__':
    main()
