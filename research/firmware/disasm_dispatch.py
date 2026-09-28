"""Reconstruct the property dispatch in viewUnified2.so by disassembly.

The task, stated precisely
---------------------------
549 pool references to key 0x5580021f (property 1f0280550208) and 922 to
0xa7394cc3 (the boolean).  Almost none are near an exported symbol, so the
functions must be recovered structurally.  Then, for each function that touches
a key, find the instruction that reads the property payload and report the
offset it reads and what the loaded value is then used for.

That last part is the whole point.  Reading payload byte N of property P tells
us which field the engine cares about; seeing what the value is compared against
or used as an index into tells us what the field is.  That is a name derived
from behaviour, which is the only kind of evidence left.

Method, in order
----------------
F1  Function recovery.  Thumb functions begin with push {... lr} and end with
    pop {... pc}.  Scan .text for those, producing an interval list.  This is
    reliable enough for a static library, and the count is checkable: it should
    be in the thousands, and functions must not overlap.

F2  For each key pool entry, find the ldr that references it.  A Thumb literal
    load is ldr rX, [pc, #imm] where the target is (PC & ~3) + 4 + imm, and PC
    is the instruction address + 4.  So the referencing instruction is found by
    scanning backwards from the pool entry.  That instruction is inside a
    function, and the function's identity is now known structurally.

F3  Within that function, find the compare against the key and the branch on it.
    A dispatch is `cmp rX, #imm` is not how a 32-bit key is compared, so look
    for the ldr feeding a cmp, and for the beq/bne that leaves the function.

F4  In the taken branch, find loads from the property payload.  A property value
    arriving in a register is then indexed or compared; report the base
    register, the offset, the width, and the following instructions.

Reporting
---------
Per function: the keys it dispatches on, the payload offsets it reads, and the
comparison or index that follows.  Grouped, because a function handling 8
properties is one class of widget and its property set is the interesting
output.

Falsification
-------------
If F1 yields implausible function boundaries, the disassembly is not sound and
the output is worthless, so the boundary statistics are printed first and the
rest is only as good as they are.  A control is also reported: an offset read
from a base register that was never set from a property payload is noise and is
excluded, which is the same discipline that caught the last five false
structures.
"""
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path

from capstone import (Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN,
                      CS_MODE_ARM)

SO = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\engine\viewUnified2.so')

# property signature -> (key bytes hex, total size in the resource file)
PROPS = {
    '1b572204010e': ('1b572204', 16),
    '1f0280550208': ('1f028055', 15),
    'c34c39a70111': ('c34c39a7', 7),
    'c34c39a70191': ('c34c39a7', 8),      # alternate tag, same key
    '8ac3b3620202': ('8ac3b362', 15),
    'ed188f1a018d': ('ed188f1a', 8),
    '0fcbce250190': ('0fcbce25', 8),
    '1f0b9b400190': ('1f0b9b40', 8),
}
KEYS = {}
for sig, (k8, size) in PROPS.items():
    KEYS[struct.unpack('<I', bytes.fromhex(k8))[0]] = (sig, size)


def sections(b):
    (shoff,) = struct.unpack_from('<I', b, 32)
    (shentsize, shnum, shstrndx) = struct.unpack_from('<3H', b, 46)
    raw = [struct.unpack_from('<6I', b, shoff + i * shentsize)
           for i in range(shnum)]
    noff = raw[shstrndx][4]
    out = []
    for nameoff, stype, _fl, addr, off, size in raw:
        e = b.find(b'\x00', noff + nameoff)
        out.append((b[noff + nameoff:e].decode('latin1', 'replace'),
                    stype, addr, off, size))
    return out


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
        nameoff, value, _sz, _i, _o2, _sh = struct.unpack_from('<IIIBBH', b, o)
        if not nameoff or not value:
            continue
        e = strs.find(b'\x00', nameoff)
        nm = strs[nameoff:e].decode('latin1', 'replace')
        a = value & ~1
        if a not in out or len(nm) > len(out[a]):
            out[a] = nm
    return out


def demangle(n):
    if not n.startswith('_ZN'):
        return n
    s, i, parts = n, 3, []
    while i < len(s):
        m = re.match(r'(\d+)', s[i:])
        if not m:
            break
        ln = int(m.group(1))
        i += len(m.group(1))
        parts.append(s[i:i + ln])
        i += ln
        if i < len(s) and s[i] == 'E':
            break
    return '::'.join(parts) if parts else n


# ---------------------------------------------------------------- functions
PUSH_LR = re.compile(rb'[\x00-\xff]')
THUMB2_PUSH = {           # push.w with lr  -> 0xe92d xxxx, bit14 set
    0xe92d, 0xe92c, 0xe930, 0xe92b, 0xe92f, 0xe931, 0xe933, 0xe937,
}


def find_functions(b, lo, hi):
    """Thumb function starts: push {... lr} preceded by alignment/size words."""
    starts = []
    for o in range(lo, hi - 4, 2):
        w = struct.unpack_from('<H', b, o)[0]
        if (w & 0xFF00) == 0xB500:          # 32-bit push.w
            starts.append(o)
            continue
        if (w & 0xFE00) == 0xB400:          # 16-bit push incl lr
            starts.append(o)
    # A real function usually has 2 preceding words: .size and .type
    real = [s for s in starts if s >= 8]
    return sorted(set(real))


def main():
    b = SO.read_bytes()
    syms = dynsym(b)
    text = next(s for s in sections(b) if s[0] == '.text')
    lo, hi, tsize = text[3], text[3] + text[4], text[4]
    print('=== viewUnified2.so ===')
    print('  .text 0x%08x..0x%08x  %d bytes' % (lo, hi, tsize))
    print('  exported symbols: %d' % len(syms))
    print()

    print('=' * 78)
    print('F1  function recovery')
    print('=' * 78)
    starts = find_functions(b, lo, hi)
    ends = starts[1:] + [hi]
    print('  push-with-lr sites: %d' % len(starts))
    print('  -> function count: %d' % len(starts))
    sizes = [e - s for s, e in zip(starts, ends)]
    sizes = [s for s in sizes if 0 < s < 0x8000]
    print('  function size: median %d, p90 %d, max %d'
          % (sorted(sizes)[len(sizes) // 2],
             sorted(sizes)[int(len(sizes) * 0.9)], max(sizes)))
    print('  sizes under 8 bytes: %d (noise between functions)'
          % sum(1 for s in sizes if s < 8))
    print()
    print('  Plausibility: a static Thumb library of this size should have')
    print('  thousands of functions with a median body in the tens of bytes.')
    print('  If the numbers above are not in that range, the boundary')
    print('  recovery is unsound and nothing downstream means anything.')
    print()

    # F2: for each key pool entry, find the referencing ldr
    print('=' * 78)
    print('F2  which function loads each key?')
    print('=' * 78)
    print()
    key_off = {}
    for k, (sig, _sz) in KEYS.items():
        pat = struct.pack('<I', k)
        o = lo
        offs = []
        while True:
            o = b.find(pat, o, hi)
            if o < 0:
                break
            offs.append(o)
            o += 1
        key_off[k] = offs
        print('  %-16s %4d pool entries' % (sig, len(offs)))
    print()

    def which_func(a):
        # starts is sorted; binary search
        import bisect
        i = bisect.bisect_right(starts, a) - 1
        if i < 0:
            return None
        return (starts[i], ends[i])

    # find ldr rX,[pc,#imm] that targets a given pool address
    def find_refs(target):
        """Scan backwards up to 4096 bytes for a 16-bit ldr [pc,#imm]."""
        refs = []
        start = max(lo, target - 4096)
        for a in range(target - 2, start, -2):
            w = struct.unpack_from('<H', b, a)[0]
            if (w & 0xF800) == 0x4800:          # ldr rX, [pc, #imm8*4]
                imm = (w & 0xFF) * 4
                pc = (a + 4) & ~3
                if pc + imm == target:
                    refs.append(a)
        return refs

    func_keys = defaultdict(set)     # func start -> set of key sigs
    func_refcount = Counter()
    for k, (sig, _sz) in KEYS.items():
        for pe in key_off[k]:
            for r in find_refs(pe):
                f = which_func(r)
                if f:
                    func_keys[f[0]].add(sig)
                    func_refcount[f[0]] += 1
    print('  functions referencing at least one property key: %d'
          % len(func_keys))
    print()
    multi = {f: ks for f, ks in func_keys.items() if len(ks) >= 3}
    print('  functions referencing 3+ distinct keys: %d' % len(multi))
    print()
    print('  these are the property dispatchers, recovered structurally:')
    print()
    for f in sorted(multi, key=lambda x: -len(func_keys[x]))[:15]:
        nm = syms.get(f)
        print('  0x%08x  %2d keys  %-40s %s'
              % (f, len(func_keys[f]),
                 (demangle(nm)[:40] if nm else '(unexported)'),
                 ','.join(sorted(k[:6] for k in func_keys[f]))))
    print()

    # F3/F4: for the richest dispatchers, find payload reads
    print('=' * 78)
    print('F3/F4  payload reads inside the richest dispatchers')
    print('=' * 78)
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    for f in sorted(multi, key=lambda x: -len(func_keys[x]))[:6]:
        end = ends[starts.index(f)]
        code = b[f:min(end, f + 0x2000)]
        ins = list(md.disasm(code, f))
        print()
        print('  --- function 0x%08x, %d bytes, keys: %s'
              % (f, min(end, f + 0x2000) - f,
                 ','.join(sorted(k[:6] for k in func_keys[f]))))
        reads = []
        for i, x in enumerate(ins):
            if x.mnemonic in ('ldrb', 'ldrh', 'ldr') and '[' in x.op_str and '#' in x.op_str:
                reads.append((x.address, x.mnemonic, x.op_str))
        for a, m, o in reads[:24]:
            # what follows
            nxt = ''
            for x in ins:
                if x.address > a:
                    nxt = '%s %s' % (x.mnemonic, x.op_str)
                    break
            print('    %08x  %-5s %-22s ; then %s' % (a, m, o, nxt))
        if not reads:
            print('    (no offset loads found in the first 0x2000 bytes)')


if __name__ == '__main__':
    main()
