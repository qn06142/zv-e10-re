"""Resolve VDF command methods to real functions, by name.

Supersedes the vdf_align / vtable_probe / rawdump / vdf_simple / vdf_execute /
vdf_strref / vdf_strref2 / vdf_strref3 / vdf_pat / vdf_inner / vdf_bright /
bright_lut one-offs from this investigation, all of which now live here or in
thumb.py.  Kept as a single tool because the interesting output is a table.

Method
------
The `virtual VDF::VDF_ERR VDF::Class::Method(...)` strings are LOG strings
carrying a full C++ signature, so they are referenced pc-relative and resolve
to genuine code -- unlike RTTI type names, which are only reachable through the
typeinfo chain.  The reference encoding is implemented and regression-tested in
thumb.pcrel_strrefs.

Two things this file deliberately does NOT claim:
  * that vtable slot [k] identifies a method.  The vtables at 0x00FBB0F8 etc.
    decode cleanly at (stored & ~1) - BASE, and slot [-1] matches the typeinfo
    exactly, but the per-class slots do NOT line up with the Execute/Activate
    addresses found here (SetPanelReverse slot[5] = 0x0071E632, its Activate
    is 0x00151CBA).  Treat slot index as unidentified.
  * that a panel command can be called.  See 03-binaries.md.
"""
import re
import struct
import sys
import pathlib
from pathlib import Path

ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]

sys.path.insert(0, str(Path(__file__).parent))
from thumb import mkdis, pcrel_strrefs, walk, calls_of, is_prologue         # noqa: E402

BASE = 0x635C6000
av = (ROOT_REPO / 'dumps' / 'av-cam.bin.bak').read_bytes()
md = mkdis()

print('=== pc-relative reference map ===')
refs = pcrel_strrefs(md, av)
print('  %d targets\n' % len(refs))

pat = rb'virtual VDF::VDF_ERR VDF::[A-Za-z]+::(Execute|Activate)\('
rows = []
for m in re.finditer(pat, av):
    mo = m.start()
    st = av.rfind(b'\x00', 0, mo)
    st = 0 if st < 0 else st + 1
    site = None
    for probe in (mo, st):
        if probe in refs:
            site = refs[probe][0]
            break
    sig = m.group().decode('latin1')
    name = sig.split('(')[0].strip().split()[-1]
    rows.append((mo, name, site))

print('=== %d signature strings ===' % len(rows))
res = 0
for mo, name, site in sorted(rows, key=lambda r: r[0]):
    if site is None:
        print('  %-52s UNRESOLVED' % name[:52])
        continue
    res += 1
    fn = site
    for q in range(site, max(0x1000, site - 0x400), -2):
        hw = struct.unpack_from('<H', av, q)[0]
        if ((hw & 0xFF00) == 0xB500 and (hw & 0x0080)) or hw == 0xE92D \
                or (hw & 0xFF00) == 0xE800:
            fn = q
            break
    body = walk(md, av, fn, 0x1000)
    print('  %-52s fn 0x%08x  ref@0x%08x  %4d insn  %2d call(s)'
          % (name[:52], fn, site, len(body), len(calls_of(body))))
print('\n%d of %d resolved' % (res, len(rows)))

print('\n=== disassembly of a named method ===')
for want in sys.argv[1:]:
    for mo, name, site in rows:
        if want.lower() in name.lower() and site is not None:
            fn = site
            for q in range(site, max(0x1000, site - 0x400), -2):
                hw = struct.unpack_from('<H', av, q)[0]
                if ((hw & 0xFF00) == 0xB500 and (hw & 0x0080)) or hw == 0xE92D \
                        or (hw & 0xFF00) == 0xE800:
                    fn = q
                    break
            print('\n--- %s  fn=0x%08x ---' % (name, fn))
            for i in walk(md, av, fn, 0x1000):
                print('  0x%08x  %-12s %-9s %s'
                      % (i.address, i.bytes.hex(' '), i.mnemonic, i.op_str))
