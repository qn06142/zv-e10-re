"""Is the Golf Shot code reachable from the patch site at all?

The patch lives in /system/av-cam.bin (nflasha3, ORIL container, 17 MB).
The CamMode* classes were found in the 2025 front end, which was carved
from nflasha15.img -> /usr, i.e. elf_05610c00.so.  If Golf Shot lives in
that other file, no branch inside av-cam.bin can reach it: different
process, different address space, different file.
"""
import re
from pathlib import Path

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
AV = BASE / 'dumps' / 'av-cam.bin.bak'

TERMS = [b'CamModeGolfShot', b'GolfShot', b'GOLF', b'golf', b'CamMode', b'MotionShot',
         b'Motion Shot', b'ObjRenderer', b'CamUser']

print('=== av-cam.bin (vanilla, 17 MB) - the file the patch lives in ===')
av = AV.read_bytes()
print('  size %d' % len(av))
for t in TERMS:
    print('  %-16s %d hit(s)' % (t.decode(), av.count(t)))
print()

print('=== CamMode-ish strings actually present in av-cam.bin ===')
found = set()
for m in re.finditer(rb'[\x20-\x7e]{5,80}', av):
    s = m.group().decode('ascii')
    if 'CamMode' in s or 'Golf' in s or 'MotionShot' in s:
        found.add((m.start(), s))
for off, s in sorted(found)[:30]:
    print('  0x%08x  %s' % (off, s))
print('  (%d total)' % len(found))
print()

print('=== the 2025 front end, for comparison ===')
fe = BASE / 'dumps' / 'camera_2025' / 'usr_lib_raw' / 'elf_05610c00.so'
if fe.exists():
    b = fe.read_bytes()
    print('  %s  %d bytes' % (fe.name, len(b)))
    for t in TERMS:
        print('  %-16s %d hit(s)' % (t.decode(), b.count(t)))
else:
    print('  (front-end ELF not found at %s)' % fe)
print()

print('=== BL range check: can a Thumb BL from 0xaa15a reach across files? ===')
print('  Thumb-2 BL encodes a signed 25-bit word-scaled offset.')
print('  range = +/-16 MB from the instruction.')
print('  av-cam.bin is %.1f MB, so a BL CAN span the whole file.' % (len(av) / 1e6))
print('  But it cannot leave the file: there is no mapping from av-cam.bin')
print('  offsets into the address space of a separate process/ELF.')
