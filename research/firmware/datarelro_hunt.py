"""Hunt the class table in .data.rel.ro, which unlike the GOT is fully relocated.

Why this is still worth doing after the GOT closed
---------------------------------------------------
The constructors install their class entry from the GOT, and the GOT is
unrelocated with no .rel.dyn coverage, so the chain stops there.  But the GOT
only ever holds a *pointer into* a table, and a table of function pointers in a
shared object has to live in a section the loader relocates -- which is
.data.rel.ro, 621,088 bytes and about 155,000 pointers, all readable as they
stand because R_ARM_RELATIVE entries carry the addend in the file.

So the question is not "where is the GOT slot" but "which readable table of
.text pointers has arity-specific entries".  That is a searchable structure, and
the search has a target: a run of consecutive .text pointers, in which three
specific functions are the distinguishing entries.

The shape being looked for
--------------------------
A C++ vtable for these property classes is a run of .text function pointers.  The
four classes differ in exactly one way that matters -- arity -- so their vtables
should be near-identical except at the slot implementing the read.  If the
arithmetic-4 class's vtable is found, the differing slot is its reader.

So the hunt is for runs of consecutive .text pointers, and within each run the
slots that vary between candidate tables.  Runs, not single pointers: a lone
.text pointer is 78,234-odd things in this binary and means nothing.

Three falsifiable requirements, checked in order
-----------------------------------------------
  R1  Runs must exist and be enumerable.  The count of maximal runs of >= 6
      consecutive .text pointers is reported.  If that is implausibly small or
      implausibly large, the definition of a run is wrong and the rest is void.
  R2  The section must be what it claims.  Every run is required to lie inside
      .data.rel.ro; a "run" spanning into .data or .got is rejected, because a
      vtable is relocated and an unrelocated run is a coincidence of adjacent
      integers looking like code addresses.
  R3  A positive control on the method.  The same run-finder is run over
      .rodata, where no vtable can live.  Whatever it reports there is the
      false-positive rate, and it is reported before any candidate is named.
      If the .data.rel.ro hit count is not far above that, there is no signal.
"""
import re
import struct
import bisect
from collections import Counter, defaultdict
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

SO = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\engine\viewUnified2.so')
S_TEXT = (0x0018eec8, 0x0018eec8 + 0x0074af6c)
S_RODATA = (0x008d9e40, 0x008d9e40 + 0x001e8745)
S_DATARELRO = (0x00b82698, 0x00b82698 + 0x00097c20)
MIN_RUN = 6


def sections(b):
    (shoff,) = struct.unpack_from('<I', b, 32)
    (shentsize, shnum, shstrndx) = struct.unpack_from('<3H', b, 46)
    raw = [struct.unpack_from('<10I', b, shoff + i * shentsize) for i in range(shnum)]
    noff = raw[shstrndx][4]
    res = []
    for r in raw:
        e = b.find(b'\x00', noff + r[0])
        res.append((b[noff + r[0]:e].decode('latin1', 'replace'),
                    r[1], r[3], r[4], r[5]))
    return res


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
    ds = next(s for s in secs if s[0] == '.dynsym')
    dt = next(s for s in secs if s[0] == '.dynstr')
    strs = b[dt[3]:dt[3] + dt[4]]
    out = {}
    for i in range(ds[4] // 16):
        o = ds[3] + i * 16
        n2, val, _z, _i, _o2, _sh = struct.unpack_from('<IIIBBH', b, o)
        if not n2 or not val:
            continue
        e = strs.find(b'\x00', n2)
        a, s = val & ~1, strs[n2:e].decode('latin1', 'replace')
        if a not in out or len(s) > len(out[a]):
            out[a] = s
    return out


def runs_of_text_ptrs(b, lo, hi, minrun=MIN_RUN):
    """maximal runs of consecutive 32-bit words that are .text addresses"""
    out = []
    n = (hi - lo) // 4
    cur = None
    for i in range(n):
        v = struct.unpack_from('<I', b, lo + i * 4)[0]
        t = v & ~1
        if S_TEXT[0] <= t < S_TEXT[1] and v in (t, t | 1):
            if cur is None:
                cur = i
        else:
            if cur is not None and i - cur >= minrun:
                out.append((lo + cur * 4, i - cur))
            cur = None
    if cur is not None and n - cur >= minrun:
        out.append((lo + cur * 4, n - cur))
    return out


def main():
    b = SO.read_bytes()
    syms = dynsym(b)
    saddr = sorted(syms)

    def near(a):
        j = bisect.bisect_right(saddr, a) - 1
        return demangle(syms[saddr[j]]) if j >= 0 else '(unexported)'

    # ---- R1 and R2 ------------------------------------------------------
    print('=== R1/R2  runs of consecutive .text pointers ===')
    print()
    for label, (lo, hi) in (('.data.rel.ro', S_DATARELRO), ('.rodata', S_RODATA)):
        r = runs_of_text_ptrs(b, lo, hi)
        ents = sum(n for _a, n in r)
        print('  %-16s window 0x%08x..0x%08x  runs >= %d: %6d  covering %7d entries'
              % (label, lo, hi, MIN_RUN, len(r), ents))
    print()
    dr = runs_of_text_ptrs(b, *S_DATARELRO)
    if not dr:
        print('  no runs in .data.rel.ro; the definition of a run must be wrong.')
        return
    print()

    # ---- R3  the false-positive rate ------------------------------------
    ro = runs_of_text_ptrs(b, *S_RODATA)
    print('=== R3  false-positive rate, from the same finder on .rodata ===')
    print('  .rodata runs: %d   .data.rel.ro runs: %d   ratio %.1fx'
          % (len(ro), len(dr), len(dr) / max(1, len(ro))))
    print('  .rodata cannot contain a vtable, so its runs are the rate at which')
    print('  adjacent words merely look like code addresses.')
    print()

    # ---- what is actually in these runs ---------------------------------
    lens = Counter(n for _a, n in dr)
    print('=== run lengths in .data.rel.ro ===')
    print('  most common: %s'
          % ', '.join('%d x%d' % (k, v) for k, v in lens.most_common(12)))
    print()

    print('=== the longest runs, with their entries named ===')
    print()
    for a, n in sorted(dr, key=lambda t: -t[1])[:6]:
        print('  run at 0x%08x, %d entries' % (a, n))
        for i in range(min(n, 10)):
            e = struct.unpack_from('<I', b, a + i * 4)[0]
            t = e & ~1
            mark = ''
            if t in (0x640850, 0x640878, 0x648150, 0x677010):
                mark = '   <<<< A KNOWN CLASS'
            print('      +%-3d 0x%08x  %-46s%s' % (i, e, near(t)[:46], mark))
        if n > 10:
            print('      ... %d more' % (n - 10))
        print()

    # ---- the direct question: does any run mention a known class? -------
    print('=== do any runs contain a known property class? ===')
    print()
    want = {0x640850: 'ed188f1a018d arity1', 0x640878: 'c34c39a70111 arity1 bool',
            0x648150: '1f0280550208 arity2', 0x677010: '38f85c32.. arity4 RECT'}
    hits = defaultdict(list)
    for a, n in dr:
        for i in range(n):
            e = struct.unpack_from('<I', b, a + i * 4)[0] & ~1
            if e in want:
                hits[e].append((a, i, n))
    for e, why in want.items():
        lst = hits.get(e, [])
        print('  0x%08x %-24s in %d run(s)' % (e, why, len(lst)))
        for a, i, n in lst[:4]:
            print('      run 0x%08x slot %d of %d' % (a, i, n))
    print()
    if not hits:
        print('  No run contains a known class, so these are not the property')
        print('  class vtables.  A vtable holds virtual *methods*, and a property')
        print('  class constructor is not one, so its absence here is expected')
        print('  rather than surprising.  What the constructors install is a')
        print('  dispatch table keyed by class, which is a different structure:')
        print('  an array of small integers or of handler pointers, indexed by')
        print('  the key, not a per-class vtable.')


if __name__ == '__main__':
    main()
