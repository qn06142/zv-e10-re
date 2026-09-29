"""Brute-force resolve the VDF Execute/Activate log strings to code.

The previous sweep failed to resolve 34 of 36 strings because it only walked
outward from function-prologue seeds and stopped at returns -- a coverage
limit, not a data limit (all 35 strings are inside the text region).

This does no walking at all.  It linearly scans every 2-byte-aligned position
for a Thumb LDR (literal), computes the pool address, and reads the word.  If
that word equals a target string's runtime address, we have the exact
instruction that loads it -- no function-boundary assumptions required.  We
then scan backwards for the nearest prologue to name the containing function.
"""
import re
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from thumb import mkdis, dis1, walk, calls_of, is_prologue                 # noqa: E402

BASE = 0x635C6000
av = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
N = len(av)
TEXT_END = 0xAED000
md = mkdis()

# ---- target strings ------------------------------------------------------
logstr = {}
for m in re.finditer(rb'virtual VDF::VDF_ERR VDF::[A-Za-z]+::(Execute|Activate)\(', av):
    logstr[m.start() + BASE] = m.group().decode('latin1')
print('=== %d Execute/Activate log strings ===' % len(logstr))
print()

# ---- linear scan for LDR-literal loads -----------------------------------
# Thumb LDR (literal) T1: 01001 Rt imm8  ->  (hw & 0xF800) == 0x4800
#   pool = ((addr + 4) & ~3) + imm8 * 4
# Thumb LDR.W (literal) T2: 11111 00 U 1111 Rt imm12
#   pool = (addr + 4) + imm12
sites = defaultdict(list)          # pool_value -> [load instruction addrs]
for addr in range(0x1000, min(TEXT_END, N) - 4, 2):
    hw = struct.unpack_from('<H', av, addr)[0]
    if (hw & 0xF800) == 0x4800:
        pool = ((addr + 4) & ~3) + (hw & 0xFF) * 4
    elif (hw & 0xFF7F) == 0xF85F:
        imm12 = struct.unpack_from('<H', av, addr + 2)[0] & 0x0FFF
        u = (hw >> 7) & 1
        pool = (addr + 4) + (imm12 if u else -imm12)
    else:
        continue
    if 0 <= pool <= N - 4:
        sites[struct.unpack_from('<I', av, pool)[0]].append(addr)

print('  scanned %d addresses, %d distinct pool values'
      % (min(TEXT_END, N) - 0x1000, len(sites)))
print()

# ---- backward scan for the containing function ---------------------------
def func_start_for(site):
    """Nearest prologue at or before `site` within 0x400 bytes."""
    best = None
    for q in range(site, max(0x1000, site - 0x400), -2):
        if is_prologue(av, q):
            best = q
            break
    return best if best is not None else site


print('=== Execute/Activate log strings -> containing functions ===')
resolved = {}
for off, s in sorted(logstr.items()):
    hits = sites.get(off)
    if not hits:
        print('  %-52s  no literal load found' % s.split('(')[0].strip().split()[-1][:52])
        continue
    name = s.split('(')[0].strip().split()[-1]
    site = hits[0]
    fn = func_start_for(site)
    body = walk(md, av, fn, 0x800)
    cl = calls_of(body)
    resolved[name] = (fn, cl, site)
    print('  %-52s fn 0x%08x  ld@0x%08x  %d insn, %2d call(s)'
          % (name[:52], fn, site, len(body), len(cl)))

print()
print('=== %d of %d resolved ===' % (len(resolved), len(logstr)))
print()

PANEL = [n for n in resolved if 'Panel' in n or 'Osd' in n or 'Luminance' in n]
print('=== panel/OSD methods found: %d ===' % len(PANEL))
for n in sorted(PANEL):
    fn, cl, site = resolved[n]
    print('  %-52s 0x%08x' % (n[:52], fn))
print()

# ---- the target: SetPanelReverse -----------------------------------------
print('=== SetPanelReverse / SetPanelBrightness full disassembly ===')
for want in ('VDF::VdfDisplayCmdSetPanelReverse::Activate',
             'VDF::VdfDisplayCmdSetPanelBrightness::Activate',
             'VDF::VdfDisplayCmdSetPanelBrightness::Execute',
             'VDF::VdfDisplayCmdSetOsdAlpha::Execute'):
    if want not in resolved:
        continue
    fn, cl, site = resolved[want]
    print('\n--- %s  fn=0x%08x  loads-string@0x%08x' % (want, fn, site))
    for i in walk(md, av, fn, 0x200):
        print('  0x%08x  %-12s %-8s %s'
              % (i.address, i.bytes.hex(' '), i.mnemonic, i.op_str))
