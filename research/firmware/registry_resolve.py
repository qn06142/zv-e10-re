"""Resolve the property registry in viewUnified2.so to real function names.

The chain
---------
Previous rounds established:

  * the registry is in viewUnified2.so, visible at 0x648774 as contiguous
    groups of property keys, with a non-key value in the slot after the two
    layout properties 1b572204010e / 1f0280550208
  * that value, 0x72dc12e4, recurs in every run inspected -- a field constant
    across all records of a table is a dispatch target, not data
  * viewUnified2.so exports 4,181 dynamic symbols and its .rodata contains RTTI
    name encodings like N19LG_viewbeautyeffect25LayoutFace_Selection_BaseE
  * the boolean key 0xa7394cc3 is a .text immediate, not a rodata constant, so
    the association has to run through code rather than a data table
  * libObj.so has no DWARF and does not contain the boolean key at all

So the route is: take the registry, read the value slot as a pointer, and resolve
that pointer through .dynsym.  A pointer to ux::wgtsys::LayoutConverter::something
names the property by what the code does with it.  That is a real name, from a
symbol table, not a correlation.

Why this should work when correlation did not
--------------------------------------------
Three rounds of inference on the boolean produced one falsified hypothesis, one
unsupported, and one that survived on a weak statistic.  The problem there was
that a name was never available.  Here a name is available if the pointer
resolves, and if it does not resolve the honest answer is that the registry
stores something other than a code address -- which is itself a finding.

Details that decide it
----------------------
Thumb.  This is an ARMv7 Thumb library, so a code address has bit 0 set when
stored in a table.  0x72dc12e4 has bit 0 clear, so either it is a plain address
or not code at all.  Both cases are reported.  The dynamic symbol table gives
values that are already masked, so the comparison tries the raw value, the value
with bit 0 cleared, and the value minus 1.

The registry shape also has to be pinned rather than assumed.  The previous run
grouped keys by proximity, which is a guess.  Here the grouping is done by
finding runs of known keys separated by a bounded gap, then reading the word
immediately after each run as a candidate value.  If the values are consistent
across runs, the shape is confirmed; if they scatter, it is not a table and that
is reported.

Also worth extracting while the pointers are in hand: the class of each
registered property, since RTTI names like GEN_Button and LayoutableWidgetBase
tell us what kind of object each key belongs to.  That alone answers "what kind
of property is this" even if the handler name is opaque.
"""
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path

ENG = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\engine')
SO = ENG / 'viewUnified2.so'

KNOWN = {
    '1b572204010e': 16, '1f0280550208': 15, 'c34c39a70111': 7,
    '8ac3b3620202': 15, 'ed06f4340100': 7, 'ec18a67a0290': 11,
    'e0435a90018d': 8, '2146adbf018d': 8, '49760d41018d': 8,
    'dbcf0a6c018d': 8, '0fcbce250190': 8, 'ed188f1a018d': 8,
    '4a311dea018c': 8, '7fb68c7f0190': 8, '82d530c60190': 8,
    '03193943018c': 8, '547e85a6018c': 8, '2dac7cb2018c': 8,
    '571c3df3018c': 8, '94899f21018d': 8, '0d4d93430190': 8,
    'd7520f8d018d': 8, 'ae338fba018d': 8, '3254afad018c': 8,
    '1f0b9b400190': 8, 'c3bd3492018d': 8, 'a99afb240190': 8,
    '9975ed000190': 8, '27d4bdf90190': 8, 'b62031c60190': 8,
    'a77eda3b0190': 8, '6b7bfc950111': 7, '78e18641018d': 8,
    '210268a50290': 10, '39b64d380190': 8, '87d407b40190': 8,
    '3efca0c00190': 8, 'cc20b27d0190': 8, '94891ba0018d': 8,
    '3925bfa00401': 17, '3dca858a0190': 8, 'd7e986ec0208': 15,
    '174a483d0190': 8, '4dc0baf80190': 8, 'eb099cef0102': 10,
    'eb099cef0101': 8, '1c0034cb0190': 8, '54eb60d70111': 7,
    '3ea961a70111': 7, '3c19f799018d': 32, '38f85c320408': 40,
    'dd387635028d': 22, 'c34c39a70191': 8, 'eb2c0d180190': 8,
    '95753a130101': 8, '11ddc5e2018c': 8, '448671460111': 7,
    'fd2fad3d0111': 7,
}
KEYS = {}
for s in KNOWN:
    KEYS[struct.unpack('<I', bytes.fromhex(s[:8]))[0]] = s
BOOL_KEY = 0xa7394cc3
LAYOUT_A = 0x0422571b
LAYOUT_B = 0x5502801f


def sections(b):
    (shoff,) = struct.unpack_from('<I', b, 32)
    (shentsize, shnum, shstrndx) = struct.unpack_from('<3H', b, 46)
    if not shoff or not shnum:
        return []
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
    """address -> [names], from .dynsym/.dynstr."""
    secs = sections(b)
    ds = next((s for s in secs if s[0] == '.dynsym'), None)
    dt = next((s for s in secs if s[0] == '.dynstr'), None)
    if not ds or not dt:
        return {}
    strs = b[dt[3]:dt[3] + dt[4]]
    out = defaultdict(list)
    n = ds[4] // 16
    for i in range(n):
        o = ds[3] + i * 16
        nameoff, value, _sz, _info, _other, _shndx = struct.unpack_from('<IIIBBH', b, o)
        if not nameoff or not value:
            continue
        e = strs.find(b'\x00', nameoff)
        nm = strs[nameoff:e].decode('latin1', 'replace')
        out[value & ~1].append(nm)
        out[value].append(nm)
    return out


def demangle(name):
    """Minimal Itanium demangle good enough for _ZN...E forms."""
    if not name.startswith('_ZN'):
        return name
    s = name
    i = 3
    parts = []
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
    return '::'.join(parts) if parts else name


def find_runs(b):
    """Runs of known-key words, grouped by a bounded gap."""
    hits = []
    for o in range(0, len(b) - 3, 4):
        v = struct.unpack_from('<I', b, o)[0]
        if v in KEYS:
            hits.append((o, v))
    runs = []
    cur = [hits[0]] if hits else []
    for h in hits[1:]:
        if h[0] - cur[-1][0] <= 64:
            cur.append(h)
        else:
            runs.append(cur)
            cur = [h]
    if cur:
        runs.append(cur)
    return runs


def main():
    b = SO.read_bytes()
    print('=== viewUnified2.so  %d bytes ===' % len(b))
    syms = dynsym(b)
    print('  dynamic symbol addresses: %d' % len(syms))
    print()
    runs = find_runs(b)
    runs = [r for r in runs if len(r) >= 3]
    print('  key runs of >=3 words: %d' % len(runs))
    print()

    # the value slot: the word right after a run of keys
    print('=' * 78)
    print('registry shape: what follows each key run?')
    print('=' * 78)
    vals = Counter()
    for r in runs[:200]:
        end = r[-1][0]
        if end + 8 <= len(b):
            v = struct.unpack_from('<I', b, end + 4)[0]
            if v not in KEYS:
                vals[v] += 1
    print('  %d distinct values in the slot after a key run' % len(vals))
    for v, n in vals.most_common(12):
        print('    0x%08x  x%d   %s' % (v, n, syms.get(v, [''])[0][:70] if v in syms else ''))
    print()
    if len(vals) == 1:
        print('  >> exactly one value across all runs: this is a table, and the')
        print('     value is a field common to every record.')
    elif len(vals) <= 3:
        print('  >> a small number of distinct values: a table with a shared')
        print('     dispatch target.')
    else:
        print('  >> values scatter, so the word after a run is not a uniform')
        print('     field. The grouping by proximity may be wrong.')
    print()

    # resolve the recurring pointer
    print('=' * 78)
    print('resolving the recurring value through .dynsym')
    print('=' * 78)
    for v, n in vals.most_common(6):
        cands = [v, v & ~1, v - 1, (v & ~1) - 1]
        hit = None
        for c in cands:
            if c in syms and syms[c]:
                hit = (c, syms[c][0])
                break
        print('  0x%08x (x%d):' % (v, n))
        if hit:
            print('     -> 0x%08x  %s' % (hit[0], demangle(hit[1])))
            print('        raw: %s' % hit[1])
        else:
            print('     -> NOT a dynamic symbol (tried %s)'
                  % ', '.join('0x%08x' % c for c in cands))
    print()

    # what class does each key belong to: use co-occurrence with RTTI-ish
    # structures, and the class of the handlers if any resolve
    print('=' * 78)
    print('per-key handler resolution, largest runs first')
    print('=' * 78)
    runs.sort(key=lambda r: -len(r))
    for r in runs[:10]:
        end = r[-1][0]
        v = struct.unpack_from('<I', b, end + 4)[0] if end + 8 <= len(b) else 0
        nm = ''
        for c in (v, v & ~1, v - 1):
            if c in syms and syms[c]:
                nm = demangle(syms[c][0])
                break
        print()
        print('  run @0x%08x  %d keys  value 0x%08x  %s'
              % (r[0][0], len(r), v, nm or '(unresolved)'))
        for o, k in r[:12]:
            print('     0x%08x  %s' % (o, KEYS[k]))
    print()

    # boolean key specifically
    print('=' * 78)
    print('the boolean key 0x%08x (%s)' % (BOOL_KEY, KEYS[BOOL_KEY]))
    print('=' * 78)
    pat = struct.pack('<I', BOOL_KEY)
    offs = []
    i = 0
    while True:
        i = b.find(pat, i)
        if i < 0:
            break
        offs.append(i)
        i += 1
    print('  %d occurrences' % len(offs))
    # find runs that contain it
    hits = [r for r in find_runs(b) if any(k == BOOL_KEY for _o, k in r)]
    print('  appears in %d key-runs' % len(hits))
    for r in hits[:5]:
        end = r[-1][0]
        v = struct.unpack_from('<I', b, end + 4)[0] if end + 8 <= len(b) else 0
        nm = ''
        for c in (v, v & ~1, v - 1):
            if c in syms and syms[c]:
                nm = demangle(syms[c][0])
                break
        print('    run @0x%08x  %d keys  -> 0x%08x  %s'
              % (r[0][0], len(r), v, nm or '(unresolved)'))
        for o, k in r:
            mark = '  <== the boolean' if k == BOOL_KEY else ''
            print('       0x%08x  %s%s' % (o, KEYS[k], mark))


if __name__ == '__main__':
    main()
