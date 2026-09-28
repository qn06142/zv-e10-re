"""Search every engine library for the four-field reader that viewUnified2.so lacks.

The blocker, stated exactly
---------------------------
The arity-4 property class was found: constructor 0x677010 in viewUnified2.so,
four word fields at 0x14/0x18/0x1c/0x20, one key.  A census of that whole library
found no four-field *reader*, and the class dispatch entry lives in an
unrelocated .got slot with no .rel.dyn coverage, so it cannot be followed from
the file either.

That leaves two possibilities that are both testable right now:

  (a) the reader is in one of the other twelve libraries, or
  (b) it is in viewUnified2.so but writes the fields in a form the detector
      cannot see.

This script tests (a) across all of them, and it does not need to know anything
about the reader in advance -- it looks for the same payload shape, arity 4, in
each library, using the same detector that was calibrated on viewUnified2.so's
three known classes.

The same shape is not the same function, so the extra work
----------------------------------------------------------
A four-word contiguous run at 0x14..0x20 is suggestive but not identifying, and in
a 21 MB library like libObj.so there will be incidental hits.  So for every
candidate the script also reports:

  * whether it calls the shared base constructor 0x1872c8 -- which is what
    distinguishes a property class from an unrelated struct, and is a strong
    filter because the property classes are a large, identifiable family;
  * the literal-pool keys loaded within a few instructions of a call to it,
    which is how the constructor is reached, and therefore how a candidate is
    tied to a property key at all.

A candidate is only interesting if it both has the shape and is reachable by a
property key.  A shape hit without a key is just a struct.

Ground truth travels with it
----------------------------
viewUnified2.so is included in the same run as a control.  Its known
constructor 0x677010 must be found, and its known arity must come out as 4.  If
the control library does not reproduce that, the run over the others means
nothing, and it is reported as such.
"""
import re
import struct
import bisect
import sys
from collections import Counter, defaultdict
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

ENG = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\engine')
BASE_CTOR = 0x1872c8
HDR = 0x10
CONTROL_CTOR = 0x677010          # must be found, arity 4, in viewUnified2.so


def sections(b):
    (shoff,) = struct.unpack_from('<I', b, 32)
    if shoff == 0 or shoff + 4 > len(b):
        return []
    (shentsize, shnum, shstrndx) = struct.unpack_from('<3H', b, 46)
    if shnum == 0 or shoff + shnum * shentsize > len(b):
        return []
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


def find_text(b):
    for n, _t, ad, _o, sz in sections(b):
        if n == '.text':
            return ad, ad + sz
    return None, None


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


def payload_fields(ins):
    reg = {'r0': 0}
    zero, fresh, out = {}, {}, {}
    for i, x in enumerate(ins):
        full = x.mnemonic + ' ' + x.op_str
        m = re.match(r'^mov\s+(r\d+),\s*(r\d+)$', full)
        if m:
            d, s = m.group(1), m.group(2)
            reg[d] = reg[s] if s in reg else None
            if reg[d] is None:
                reg.pop(d, None)
            zero[d] = zero.get(s, False)
            if s in fresh:
                fresh[d] = fresh[s]
            else:
                fresh.pop(d, None)
            continue
        m = re.match(r'^add\s+(r\d+),\s*(r\d+),\s*#(0x[0-9a-f]+|\d+)$', full)
        if m and m.group(2) in reg:
            reg[m.group(1)] = reg[m.group(2)] + int(m.group(3), 0)
            continue
        m = re.match(r'^movs?\s+(r\d+),\s*#(?:0x0+|0)$', full)
        if m:
            zero[m.group(1)] = True
            continue
        m = re.match(r'^str(b)?\s+(r\d+),\s*\[(r\d+)(?:,\s*#(0x[0-9a-f]+|\d+))?'
                     r'\](?:\s*,\s*#(0x[0-9a-f]+|\d+))?$', full)
        if m:
            isb, srcreg, base, disp, post = m.groups()
            ok = zero.get(srcreg, False) or \
                (srcreg in fresh and i - fresh[srcreg] <= 3)
            if ok and base in reg:
                off = reg[base] + (int(disp, 0) if disp else 0)
                if post:
                    reg[base] = off + int(post, 0)
                if off > HDR:
                    out[off] = 1 if isb else 4
            continue
        if re.match(r'^blx?\b', full):
            fresh['r0'] = i
            zero['r0'] = False
            continue
        m2 = re.match(r'^\S+\s+(r\d+)(?:\s*,\s*(.*))?$', full)
        if m2:
            r = m2.group(1)
            if m2.group(2) is None:
                zero.pop(r, None)
                fresh.pop(r, None)
            else:
                zero[r] = False
                fresh.pop(r, None)
    return out


def scan(path):
    b = path.read_bytes()
    lo, hi = find_text(b)
    if lo is None:
        return None
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    md.skipdata = False
    funcs = find_functions(b, lo, hi)
    four = []
    tot = bogus = 0
    decoded = {}
    for s, e in funcs:
        ins = list(md.disasm(b[s:e], s))
        decoded[s] = ins
        tot += len(ins)
        for x in ins:
            if re.match(r'^ldrb?[a-z]{2}$', x.mnemonic) and \
                    x.mnemonic not in ('ldrd', 'ldrex', 'ldrexh'):
                bogus += 1
        f = payload_fields(ins)
        w = sorted(o for o, wd in f.items() if wd == 4)
        if not w:
            continue
        a0, a1 = w[0], w[-1]
        if (a1 - a0) % 4 or set(w) != set(range(a0, a1 + 1, 4)):
            continue
        if (a1 - a0) // 4 + 1 != 4:
            continue
        four.append((s, w, any(x.mnemonic == 'blx' and
                               x.op_str == '#0x%x' % BASE_CTOR for x in ins)))
    return dict(b=b, lo=lo, hi=hi, funcs=funcs, decoded=decoded, four=four,
                tot=tot, bogus=bogus, syms=dynsym(b))


def keys_near(b, ins, target):
    """literal-pool keys loaded within 4 instructions before a call to target"""
    out = set()
    for i, x in enumerate(ins):
        if x.mnemonic not in ('bl', 'blx') or not x.op_str.startswith('#'):
            continue
        try:
            t = int(x.op_str[1:], 16)
        except ValueError:
            continue
        if t != target:
            continue
        for k in range(i - 1, max(-1, i - 5), -1):
            y = ins[k]
            if y.mnemonic.startswith('ldr') and '[pc,' in y.op_str:
                m = re.search(r'\[pc,\s*#(-?(?:0x)?[0-9a-fx]+)\]', y.op_str)
                a = (y.address & ~3) + 4 + int(m.group(1), 0)
                if 0 <= a + 4 <= len(b):
                    v = struct.unpack_from('<I', b, a)[0]
                    if HDR < v < 0xFFFF0000:
                        out.add(v)
                break
    return out


def main():
    libs = sorted(ENG.glob('*.so'), key=lambda p: -p.stat().st_size)
    print('=== the four-field shape, across every engine library ===')
    print()
    print('  %-26s %10s %8s %8s %9s' %
          ('library', 'text', 'funcs', 'arity4', 'base-ctor'))
    print('  ' + '-' * 68)
    results = {}
    for p in libs:
        r = scan(p)
        if r is None:
            print('  %-26s   (no .text)' % p.name)
            continue
        results[p.name] = r
        nc = sum(1 for _s, _w, c in r['four'] if c)
        print('  %-26s %10d %8d %8d %9d'
              % (p.name, r['hi'] - r['lo'], len(r['funcs']), len(r['four']), nc))
    print()

    # ---- control --------------------------------------------------------
    ctl = results.get('viewUnified2.so')
    print('=== control: viewUnified2.so must reproduce the known arity-4 class ===')
    print()
    if ctl is None:
        print('  control library did not scan; the whole run is void.')
        return
    got = [t for t in ctl['four'] if t[0] == CONTROL_CTOR]
    print('  0x%08x found: %s   base-ctor: %s'
          % (CONTROL_CTOR, bool(got), got[0][2] if got else '-'))
    if not got:
        print('  CONTROL FAILED -- the detector does not reproduce ground truth on')
        print('  the library it was calibrated on, so hits elsewhere mean nothing.')
        return
    print('  CONTROL PASSED')
    print()

    # ---- candidates with a key -------------------------------------------
    # The key travels with the CALL, not with the callee.  The first version of
    # this scanned each candidate's own body for a call to itself and therefore
    # found nothing -- including for viewUnified2.so's 0x677010, whose key
    # 0x325cf838 arity_verify.py had already established.  A control that can
    # only ever print "none" is not a control, so the known pairing is asserted
    # here and the run stops if it does not hold.
    print('=== control on the key-reachability test itself ===')
    print()
    ctl_keys = set()
    for s, ins in ctl['decoded'].items():
        ctl_keys |= keys_near(ctl['b'], ins, CONTROL_CTOR)
    print('  key(s) reaching 0x%08x: %s'
          % (CONTROL_CTOR,
             ' '.join(sorted(k.to_bytes(4, 'little').hex() + '..' for k in ctl_keys))
             or 'NONE'))
    if not ctl_keys:
        print('  FAILED -- the key-reachability test finds nothing even where a key')
        print('  is known to exist, so a "none" result below would be meaningless.')
        return
    print('  passed: the test does find a key where one is known.')
    print()

    print('=== arity-4 functions reachable by a property key ===')
    print()
    hits = defaultdict(set)
    for name, r in results.items():
        for s, ins in r['decoded'].items():
            for t, _w, _c in r['four']:
                if t == s:
                    continue
                k = keys_near(r['b'], ins, t)
                if k:
                    hits[(name, t)] |= k
    if not hits:
        print('  None.  No arity-4 function in any of the thirteen libraries is')
        print('  called with a literal-pool key in the five instructions before it.')
        print()
        print('  The shape detector is calibrated (the control library reproduces')
        print('  its known arity-4 class) and the key test is calibrated (it finds')
        print('  the known key above), so this is a measured result across ~45 MB')
        print('  of engine code rather than an assumption.')
    else:
        for (name, t), ks in sorted(hits.items()):
            r = results[name]
            meta = [x for x in r['four'] if x[0] == t]
            isctor = meta[0][2] if meta else '?'
            fields = ','.join(hex(o) for o in meta[0][1]) if meta else '?'
            kb = ' '.join(sorted(k.to_bytes(4, 'little').hex() + '..' for k in ks))[:60]
            print('  %-22s 0x%08x  ctor=%-5s fields %-18s keys %s'
                  % (name, t, isctor, fields, kb))
    print()


if __name__ == '__main__':
    main()
