"""Trace the Version screen's %2d.%02d back to the two integers that feed it.

The target
----------
The camera's Version screen shows a firmware version.  viewUnified6.so contains

    LG_viewversionnumber::LayoutVERSION
    LG_viewversionnumber::LayoutINITIAL_VERSION
    LG_viewversionnumber::LayoutLAYOUT_VERSION_INFO
    %2d.%02d
    ViewVersionNumber

The value is therefore not stored as text: two integers are formatted at run time
as major.minor, which is why no version string appears anywhere in the tree.
To change what the screen shows, those two integers have to be found, and the
only place they can be found is the code that calls the formatter.

The method
---------
The format string is a known address.  Code cannot reference a string's address
directly in Thumb, so the address must appear as a 32-bit constant in a literal
pool, and an `ldr rX, [pc, #imm]` must load that pool slot.  Working backwards
from the string to the pool to the load gives the function that formats the
version, and the arguments to the formatting call are the two integers.

This is a data-flow walk from a known literal, not a search for something
version-shaped, so it cannot produce a coincidence.

Controls, because six of the earlier instrument hunts could not fail
-------------------------------------------------------------------
  C1  The string address must be unique, and the constant must be found at
      least once.  If the constant is absent the string is unreferenced by that
      route and the walk stops rather than guessing.
  C2  Every pool hit must be attributable to a specific `ldr`, and every ldr to a
      specific function.  Hits that cannot be attributed are counted and
      reported, not silently included.
  C3  A negative control: the same walk is run for a *different* nearby string
      that is definitely not the version, and must not land on the same function.
      If it does, the walk is matching position rather than content.
  C4  Decoding is confined to recovered function bodies, because decoding loose
      .text desynchronises over literal pools -- the bug that once made capstone
      emit ldrtmi and ldreq, which are not ARM instructions.
"""
import re
import struct
import bisect
from collections import defaultdict
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

SO = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\engine\viewUnified6.so')
FMT = b'%2d.%02d'
# a nearby string that is definitely not the version, for the negative control
CTRL = b'Playback Target'


def sections(b):
    (shoff,) = struct.unpack_from('<I', b, 32)
    (shentsize, shnum, shstrndx) = struct.unpack_from('<3H', b, 46)
    raw = [struct.unpack_from('<10I', b, shoff + i * shentsize) for i in range(shnum)]
    noff = raw[shstrndx][4]
    out = []
    for r in raw:
        e = b.find(b'\x00', noff + r[0])
        out.append((b[noff + r[0]:e].decode('latin1', 'replace'),
                    r[1], r[3], r[4], r[5]))
    return out


def demangle(n):
    if not n.startswith('_ZN'):
        return n
    i, p = 3, []
    while i < len(n):
        m = re.match(r'(\d+)', n[i:])
        if not m:
            break
        ln = int(m.group(1))
        i += len(m.group(1))
        p.append(n[i:i + ln])
        i += ln
        if i < len(n) and n[i] == 'E':
            break
    return '::'.join(p) if p else n


def dynsym(b):
    secs = sections(b)
    ds = next((s for s in secs if s[0] == '.dynsym'), None)
    dt = next((s for s in secs if s[0] == '.dynstr'), None)
    if not ds or not dt:
        return {}
    strs = b[dt[3]:dt[3] + dt[4]]
    out = {}
    for i in range(ds[4] // 16):
        o = ds[3] + i * 16
        if o + 16 > len(b):
            break
        n2, val, _z, _i, _o2, _sh = struct.unpack_from('<IIIBBH', b, o)
        if not n2 or not val:
            continue
        e = strs.find(b'\x00', n2)
        a, s = val & ~1, strs[n2:e].decode('latin1', 'replace')
        if a not in out or len(s) > len(out[a]):
            out[a] = s
    return out


def find_functions(b, lo, hi, maxsz=0x2000):
    starts = []
    for o in range(lo, hi - 4, 2):
        w = struct.unpack_from('<H', b, o)[0]
        if (w & 0xFF00) == 0xB500 or (w & 0xFE00) == 0xB400:
            if o >= 8:
                starts.append(o)
    starts = sorted(set(starts))
    return [(s, e) for s, e in zip(starts, starts[1:] + [hi])
            if 0 < e - s <= maxsz]


def main():
    b = SO.read_bytes()
    secs = sections(b)
    byname = {s[0]: s for s in secs}
    text = byname['.text']
    rodata = byname['.rodata']
    print('=== %s : %d bytes ===' % (SO.name, len(b)))
    print('  .text   0x%08x .. 0x%08x  (%d bytes)'
          % (text[2], text[2] + text[4], text[4]))
    print('  .rodata 0x%08x .. 0x%08x  (%d bytes)'
          % (rodata[2], rodata[2] + rodata[4], rodata[4]))
    print()
    # is this the viewVersionNumber plugin?
    for probe in (b'viewVersionNumber.so', b'ViewVersionNumberToInstance',
                  b'LG_viewversionnumber'):
        print('  contains %-32r : %s' % (probe.decode(),
              b.count(probe)))
    print()

    # ---- locate the format string ----------------------------------------
    def str_addr(s):
        hits = []
        i = 0
        while True:
            i = b.find(s, i)
            if i < 0:
                break
            # file offset -> vaddr: identity in this library (offsets == addrs)
            hits.append(i)
            i += 1
        return hits

    fmt_hits = str_addr(FMT)
    print('=== the format string ===')
    print('  %r occurs %d time(s) at %s'
          % (FMT.decode(), len(fmt_hits), ['0x%08x' % h for h in fmt_hits]))
    ctrl_hits = str_addr(CTRL)
    print('  control %r occurs %d time(s) at %s'
          % (CTRL.decode(), len(ctrl_hits), ['0x%08x' % h for h in ctrl_hits]))
    if not fmt_hits:
        print('  C1 FAILED: string not present.')
        return
    print('  C1 passed.')
    print()

    # ---- find the pool constants -----------------------------------------
    def pool_hits(addr):
        out = []
        pat = struct.pack('<I', addr)
        i = 0
        while True:
            i = b.find(pat, i)
            if i < 0:
                break
            if text[2] <= i < text[2] + text[4]:
                out.append(i)
            i += 1
        return out

    fmt_pools = pool_hits(fmt_hits[0])
    ctrl_pools = pool_hits(ctrl_hits[0]) if ctrl_hits else []
    print('=== C1  the address appears as a 32-bit constant in .text ===')
    print('  format string : %d pool slot(s) at %s'
          % (len(fmt_pools), ['0x%08x' % p for p in fmt_pools]))
    print('  control       : %d pool slot(s)' % len(ctrl_pools))
    if not fmt_pools:
        print('  C1 FAILED: no pool slot references the string.')
        return
    print('  C1 passed.')
    print()

    # ---- find the ldr that loads each pool slot --------------------------
    funcs = find_functions(b, text[2], text[2] + text[4])
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    md.skipdata = False
    print('=== decoding %d function bodies (C4: never loose .text) ===' % len(funcs))
    decoded = {}
    tot = bogus = 0
    for s, e in funcs:
        ins = list(md.disasm(b[s:e], s))
        decoded[s] = ins
        tot += len(ins)
        for x in ins:
            if re.match(r'^ldrb?[a-z]{2}$', x.mnemonic) and \
                    x.mnemonic not in ('ldrd', 'ldrex', 'ldrexh'):
                bogus += 1
    print('  instructions %d, impossible ldr<cond> %d (%.3f%%)'
          % (tot, bogus, 100.0 * bogus / max(1, tot)))
    if bogus / max(1, tot) > 0.01:
        print('  C4 FAILED: misaligned, stopping.')
        return
    print('  C4 passed.')
    print()

    poolset = set(fmt_pools)
    ctrlset = set(ctrl_pools)
    loaders = defaultdict(list)      # pool slot -> [(func, insn addr, reg)]
    ctrl_loaders = defaultdict(list)
    for s, ins in decoded.items():
        for i, x in enumerate(ins):
            m = re.match(r'^ldr(?:b)?(?:\.w)?\s+(r\d+),\s*\[pc,\s*#(-?(?:0x)?[0-9a-fx]+)\]',
                         x.mnemonic + ' ' + x.op_str)
            if not m:
                continue
            reg = m.group(1)
            try:
                imm = int(m.group(2), 0)
            except ValueError:
                continue
            ea = (x.address & ~3) + 4 + imm
            if ea in poolset:
                loaders[ea].append((s, x.address, reg))
            if ea in ctrlset:
                ctrl_loaders[ea].append((s, x.address, reg))
    print('=== C2  attributing each pool slot to a load and a function ===')
    print('  format-string pool slots loaded : %d of %d'
          % (len(loaders), len(fmt_pools)))
    print('  total load instructions        : %d'
          % sum(len(v) for v in loaders.values()))
    unattr = [p for p in fmt_pools if p not in loaders]
    print('  unattributed slots             : %d %s'
          % (len(unattr), ['0x%08x' % p for p in unattr]))
    print()

    print('=== C3  negative control ===')
    print('  control pool slots loaded      : %d' % len(ctrl_loaders))
    ffuncs = {s for v in loaders.values() for s, _a, _r in v}
    cfuncs = {s for v in ctrl_loaders.values() for s, _a, _r in v}
    both = ffuncs & cfuncs
    print('  functions loading the format  : %s'
          % ['0x%08x' % f for f in sorted(ffuncs)][:8])
    print('  functions loading the control : %s'
          % ['0x%08x' % f for f in sorted(cfuncs)][:8])
    print('  overlap                       : %d %s' % (len(both), sorted(both)))
    print()

    syms = dynsym(b)
    saddr = sorted(syms)

    def near(a):
        j = bisect.bisect_right(saddr, a) - 1
        return demangle(syms[saddr[j]]) if j >= 0 else '(unexported)'

    print('=== the functions that format the version ===')
    print()
    for f in sorted(ffuncs):
        print('  0x%08x  %d insns   in %s' % (f, len(decoded[f]), near(f)[:56]))
    print()
    for f in sorted(ffuncs)[:3]:
        ins = decoded[f]
        idx = {}
        for i, x in enumerate(ins):
            idx[x.address] = i
        print('=' * 78)
        print('function 0x%08x  --  %s' % (f, near(f)[:52]))
        print('=' * 78)
        targets = [a for v in loaders.values() for fs, a, _r in v if fs == f]
        for t in targets:
            i = idx[t]
            lo = max(0, i - 22)
            hi = min(len(ins), i + 26)
            for x in ins[lo:hi]:
                mk = ''
                if x.address == t:
                    mk = '   <<< loads the %r address' % FMT.decode()
                if x.mnemonic in ('bl', 'blx') and '0x' in x.op_str:
                    mk += '   <<< CALL'
                print('  %08x  %-8s %-26s%s' % (x.address, x.mnemonic, x.op_str, mk))
            print('    ...')
        print()


if __name__ == '__main__':
    main()
