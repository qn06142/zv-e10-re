"""Recover the real function addresses for the VDF panel commands.

These N3VDF...E strings are RTTI TYPE NAMES, which is why no code references
them PC-relative.  But Itanium C++ ABI RTTI is fully derivable:

    typeinfo_object = [ const vtable* vptr ][ char* name ]

and every class vtable has, at slot [-1], a pointer to its typeinfo_object.

So:
    name_addr  ->  find the 4-byte LE value == name_addr   (that is typeinfo.name)
    typeinfo   =  that slot's address - 4
    find the 4-byte LE value == typeinfo                   (that is vtable[-1])
    vtable     =  that slot's address + 4
    vtable[k]  =  the member function addresses

No relocations needed, no symbols, and it is checkable: the first few slots
should decode as plausible Thumb prologues.
"""
import re
import struct
import sys
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

sys.path.insert(0, str(Path(__file__).parent))
from thumb import dis1                                                    # noqa: E402

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
av = (BASE / 'dumps' / 'av-cam.bin.bak').read_bytes()
N = len(av)
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)


def find_word(value):
    """All file offsets whose 4-byte LE word == value."""
    pat = struct.pack('<I', value)
    out = []
    i = 0
    while True:
        i = av.find(pat, i)
        if i < 0:
            break
        out.append(i)
        i += 1
    return out


def decode_vtable(vt, label):
    print('  %s vtable at 0x%08x' % (label, vt))
    funcs = []
    k = 0
    while vt + 4 * (k + 1) <= N:
        p = struct.unpack_from('<I', av, vt + 4 * k)[0]
        if not (0x1000 <= p < 0xAED000):
            break
        funcs.append((k, p))
        k += 1
        if k > 48:
            break
    print('    %d plausible member function(s):' % len(funcs))
    for idx, p in funcs[:14]:
        ins = dis1(md, av[p:p + 4], p)
        if ins is None:
            print('      [%2d] 0x%08x  <undecodable>' % (idx, p))
        else:
            print('      [%2d] 0x%08x  %-12s %s'
                  % (idx, p, ins.mnemonic, ins.op_str[:44]))
    return funcs


TARGETS = [
    'N3VDF31VdfDisplayCmdSetPanelBrightnessE',
    'N3VDF28VdfDisplayCmdSetPanelReverseE',
    'N3VDF26VdfDisplayCmdSetPanelColorE',
    'N3VDF37VdfDisplayCmdSetPanelColorTemperatureE',
    'N3VDF24VdfDisplayCmdSetOsdAlphaE',
    'N3VDF26VdfDisplayCmdSetMonitorLutE',
    'N3VDF31VdfDisplayCmdGetPanelBrightnessE',
    'N3VDF24VdfDisplayCmdGetPanelOutE',
]

print('=== deriving member functions from RTTI (Itanium ABI layout) ===')
print()
results = {}
for t in TARGETS:
    off = av.find(t.encode())
    if off < 0:
        print('%s: NOT FOUND' % t)
        continue
    name_slots = find_word(off)
    if not name_slots:
        print('%s: name at 0x%08x but nothing points at it' % (t, off))
        continue
    got_vt = None
    for ns in name_slots:
        ti = ns - 4
        if ti < 0:
            continue
        ti_slots = find_word(ti)
        for ts in ti_slots:
            vt = ts + 4
            if 0x1000 <= vt < 0xAED000:
                got_vt = vt
                break
        if got_vt:
            break
    if not got_vt:
        print('%s: typeinfo/vtable chain not found (name slots: %s)'
              % (t, ['0x%08x' % x for x in name_slots[:4]]))
        continue
    results[t] = got_vt
    print('%s' % t)
    print('  name 0x%08x -> typeinfo 0x%08x -> vtable 0x%08x'
          % (off, name_slots[0] - 4, got_vt))
    decode_vtable(got_vt, '')
    print()

print('=== summary ===')
for t, vt in results.items():
    print('  %-46s vtable 0x%08x' % (t[:46], vt))
print()
print('%d of %d recovered' % (len(results), len(TARGETS)))
