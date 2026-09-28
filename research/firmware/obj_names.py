"""Map UXC property keys to names using libObj.so's unstripped symbol table.

The situation
-------------
We have 56 property keys from the resource files and, in libObj.so, 3,885
exported C++ symbols plus 78,234 rodata strings in an unstripped shared object
built with debug info.  The property names exist in there.  The job is to
connect them.

What we know about the target
-----------------------------
The key for c34c39a70111 is 0xa7394cc3.  Three rounds of reasoning failed to
name it: correlation narrowed it to "a per-widget-type state flag on top-level
objects" and no further; "selected" was falsified outright; "enabled" was not
supported; "visible" survived only on a weak statistic.  A name would settle it.

Four independent routes, tried in order of expected yield.  Each is reported
separately so that a negative is a result rather than a silence.

R1  demangled symbol search.  If the loader compares against an enum constant
    whose enumerator name is visible, the name is in .dynsym.  Search for
    identifiers that are plausible property names, then test whether the
    compiler emitted them adjacent to the key constants.

R2  RTTI typeinfo.  Unstripped C++ carries typeinfo names for every class.
    A class like ux::wgtsys::WidgetNode implies its members' semantics, and the
    typeinfo section is a name table that can be walked in order.

R3  debug info.  The .so was built with debug info (the rodata contains source
    file paths and function signatures in plain text, e.g.
    "virtual int OBJEFFECT::State_SfrSetPath::OnEntry(...)").  DWARF carries
    struct members with names AND byte offsets.  That is the direct route: a
    member at a known offset in a known struct, named.  It also explains why the
    rodata looks like it does -- it is not merely strings, it is .debug_str.

R4  the key-constant neighbourhood, now done properly per section.  The previous
    attempt used a printable-byte filter that caught opcodes.  Keys live in
    .text as immediates and in .rodata as literal pools; a name is a NUL-
    terminated run in .rodata or .debug_str.  Association is only claimed where
    a name is near a key AND not near other keys.

R3 is the one most likely to actually work, and the evidence that debug info is
present is already in hand: the rodata contains "State_SfrSetPath.cpp" and
full function signatures with parameter types.  That is DWARF .debug_str
content, not program strings.

Deliverable
-----------
Either a key -> name table, or a precise statement of which routes were tried,
what each ruled out, and where the answer would have to come from.  Both are
useful.  What is not useful is a plausible guess presented as a mapping, which
is the specific failure this project has hit four times.
"""
import re
import struct
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ENG = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\engine')
SO = ENG / 'libObj.so'

# property keys from the documented signature table
SIGS = {
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
KEYS = {struct.unpack('<I', bytes.fromhex(s[:8]))[0]: s for s in SIGS}
BOOL_KEY = 0xa7394cc3

VOCAB = re.compile(
    r'^(m_|s_)?(visib\w*|enable\w*|disab\w*|select\w*|focus\w*|active\w*|'
    r'state\w*|status\w*|show\w*|hide\w*|valid\w*|checked\w*|pressed\w*|'
    r'hover\w*|tap\w*|alpha\w*|transp\w*|style\w*|color\w*|colour\w*|'
    r'width\w*|height\w*|pos\w*|size\w*|rect\w*|align\w*|layer\w*|'
    r'zorder\w*|order\w*|group\w*|path\w*|font\w*|text\w*|icon\w*|'
    r'animation\w*|scroll\w*|page\w*|item\w*|index\w*|count\w*|'
    r'type\w*|kind\w*|mode\w*|flag\w*|attr\w*|prop\w*|id)$', re.I)


def demangle_all():
    """Demangle .dynsym using c++filt if present, else a small Itanium subset."""
    try:
        out = subprocess.run(['c++filt'], input=_dynsym_names(),
                             capture_output=True, text=True, timeout=120)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.splitlines()
    except Exception as e:
        print('  c++filt unavailable: %s' % e)
    return None


def _dynsym_names():
    import subprocess
    try:
        r = subprocess.run(['nm', '-D', '--defined-only', str(SO)],
                           capture_output=True, text=True, timeout=180)
        if r.returncode == 0:
            return r.stdout
    except Exception:
        pass
    return ''


def sections(b):
    (shoff,) = struct.unpack_from('<I', b, 32)
    (shentsize, shnum, shstrndx) = struct.unpack_from('<3H', b, 46)
    if not shoff or not shnum:
        return []
    raw = []
    for i in range(shnum):
        o = shoff + i * shentsize
        raw.append(struct.unpack_from('<6I', b, o))
    names_off = raw[shstrndx][4]
    out = []
    for nameoff, stype, _fl, addr, off, size in raw:
        e = b.find(b'\x00', names_off + nameoff)
        out.append((b[names_off + nameoff:e].decode('latin1', 'replace'),
                    stype, addr, off, size))
    return out


def r1_symbols(b):
    print('=' * 78)
    print('R1  demangled symbols that look like property names')
    print('=' * 78)
    ds = [s for s in sections(b) if s[0] == '.dynstr']
    if not ds:
        print('  no .dynstr')
        return []
    d = b[ds[0][3]:ds[0][3] + ds[0][4]]
    names = [t.decode('latin1', 'replace') for t in d.split(b'\x00') if len(t) >= 3]
    print('  %d symbol names' % len(names))
    # keep identifiers that read as member names
    cand = []
    for n in names:
        for part in re.split(r'[:\.\$\?]', n):
            if VOCAB.match(part):
                cand.append((n, part))
    print('  %d identifiers match a property-name vocabulary' % len(cand))
    uniq = sorted({p for _n, p in cand})
    print('  %d distinct: %s' % (len(uniq), ' '.join(uniq[:80])))
    return cand


def r2_rtti(b):
    print()
    print('=' * 78)
    print('R2  RTTI typeinfo names')
    print('=' * 78)
    ti = [m.group(0).decode('latin1', 'replace')
          for m in re.finditer(rb'N[0-9]{1,3}[A-Za-z_][\w]*E', b)]
    print('  N...E typeinfo encodings: %d' % len(ti))
    uniq = sorted(set(ti))
    print('  %d distinct' % len(uniq))
    for t in uniq[:50]:
        print('    %s' % t)


def r3_debug(b):
    print()
    print('=' * 78)
    print('R3  debug info: is DWARF present, and what is in it?')
    print('=' * 78)
    secs = sections(b)
    dbg = [(n, o, sz) for n, _t, _a, o, sz in secs if n.startswith('.debug')]
    print('  debug sections: %s' % (', '.join('%s(%d B)' % (n, s) for n, _o, s in dbg) or 'NONE'))
    if not dbg:
        print()
        print('  >> no DWARF. The rodata strings that looked like source paths')
        print('     and function signatures are program strings, not debug info.')
        return None
    # .debug_str holds every identifier
    ds = [s for s in dbg if s[0] == '.debug_str']
    if not ds:
        return None
    n, o, sz = ds[0]
    blob = b[o:o + sz]
    idents = [t.decode('latin1', 'replace') for t in blob.split(b'\x00') if len(t) >= 3]
    print('  .debug_str identifiers: %d' % len(idents))
    cand = sorted({i for i in idents if VOCAB.match(i)})
    print('  %d match a property-name vocabulary:' % len(cand))
    for c in cand[:120]:
        print('    %s' % c)
    return idents


def r4_neighbourhood(b):
    print()
    print('=' * 78)
    print('R4  names adjacent to key constants, per section')
    print('=' * 78)
    secs = sections(b)
    ro = [(o, sz, n) for n, _t, _a, o, sz in secs
          if n in ('.rodata', '.data.rel.ro') and sz]
    if not ro:
        print('  no rodata')
        return
    o0, sz0, nm = ro[0]
    print('  using %s at 0x%08x, %d B' % (nm, o0, sz0))
    # NUL-terminated runs in rodata
    runs = []
    s = 0
    blob = b[o0:o0 + sz0]
    for m in re.finditer(rb'[A-Za-z_][\w:]{5,120}', blob):
        runs.append((o0 + m.start(), m.group().decode('latin1', 'replace')))
    print('  identifier-like runs: %d' % len(runs))
    # key offsets in the whole file
    koff = defaultdict(list)
    for k in KEYS:
        pat = struct.pack('<I', k)
        i = 0
        while True:
            i = b.find(pat, i)
            if i < 0:
                break
            koff[k].append(i)
            i += 1
    print('  key constants found: %d keys, %d occurrences'
          % (len(koff), sum(len(v) for v in koff.values())))
    # for the boolean key, what is within 512 B in rodata?
    bo = koff.get(BOOL_KEY, [])
    inro = [x for x in bo if o0 <= x < o0 + sz0]
    print()
    print('  boolean key: %d total, %d inside %s' % (len(bo), len(inro), nm))
    if not inro:
        print('  it is not in rodata -- it is a .text immediate, so any name')
        print('  association has to come through the code, not a data table.')
        return
    for x in inro[:4]:
        near = [r for r in runs if abs(r[0] - x) <= 512]
        print('    key @0x%08x, identifiers within 512 B: %s'
              % (x, ' | '.join(t for _o, t in near[:6])))


def main():
    if not SO.exists():
        print('missing %s' % SO)
        return
    b = SO.read_bytes()
    print('=== libObj.so  %d bytes ===' % len(b))
    print()
    print('sections:')
    for n, t, a, o, sz in sections(b):
        if sz:
            print('  %-18s type %-10d addr 0x%08x off 0x%08x size 0x%07x'
                  % (n[:18], t, a, o, sz))
    print()
    r1_symbols(b)
    r2_rtti(b)
    idents = r3_debug(b)
    r4_neighbourhood(b)
    print()
    print('=' * 78)
    print('summary')
    print('=' * 78)
    if idents:
        print('  DWARF present with %d identifiers. Next step: walk .debug_info'
              % len(idents))
        print('  for structs whose members sit at the property offsets, and')
        print('  read the member names. That is a direct key -> name mapping.')
    else:
        print('  No DWARF. Names are only available as flat symbol and string')
        print('  tables, which give class and function names but not the byte')
        print('  offset of a property inside an object. A key -> name mapping')
        print('  would then have to come from reading the dispatch code in')
        print('  viewUnified2.so, where the registry is.')


if __name__ == '__main__':
    main()
