"""Two follow-ups:

1. Is there genuinely unused space in av-cam.bin to use as a cave?
   (Zeros are NOT automatically dead - 0x86e006 was zeros inside a live
   data table. So report candidates, and flag which look like tables.)
2. av-cam.bin contains Motion Shot stage strings. Are they referenced by
   a dispatch, i.e. is there a Motion Shot entry point in WRITABLE memory?
"""
import re
import struct
from pathlib import Path

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
av = (BASE / 'dumps' / 'av-cam.bin.bak').read_bytes()
N = len(av)

print('=== largest runs of 0x00 in av-cam.bin (cave candidates) ===')
runs = []
i = 0
while i < N:
    if av[i] == 0:
        j = i
        while j < N and av[j] == 0:
            j += 1
        if j - i >= 512:
            runs.append((i, j - i))
        i = j
    else:
        i += 1
runs.sort(key=lambda t: -t[1])
print('  %d run(s) >= 512 bytes' % len(runs))
for off, ln in runs[:12]:
    # is it inside a printable-string neighbourhood? then it is a table, not code
    ctx = av[max(0, off - 64):off]
    printable = sum(1 for b in ctx if 32 <= b < 127)
    kind = 'string/table neighbourhood' if printable > 40 else 'no strings nearby'
    print('  0x%08x  %8d bytes (0x%x)  %s' % (off, ln, ln, kind))
print()

print('=== Motion Shot strings in av-cam.bin, with context ===')
for pat in (b'Stage_MotionShot_Analysis', b'MotionShot_Base',
            b'Stage_Rcv_DistResize_MotionShotMiniYc'):
    for m in re.finditer(re.escape(pat), av):
        o = m.start()
        print('  0x%08x  %s' % (o, pat.decode()))
        s = av[o:o + 80]
        end = s.find(b'\x00')
        print('      full: %r' % (s[:end if end > 0 else 60].decode('ascii', 'replace'),))
print()

print('=== is Stage_MotionShot_* referenced by a literal pool (i.e. live)? ===')
# search all 4-byte words in the file for a value equal to (target - pc_page_delta)
# cheap approach: count how often each of these strings' addresses appears as a
# PC-relative literal.  We look for the 4-byte LE encoding of the string address
# appearing in a pool near code, which is the shape Sony uses.
for pat in (b'Stage_MotionShot_Analysis', b'MotionShot_Base'):
    o = av.index(pat)
    print('  %-30s string at 0x%08x' % (pat.decode(), o))
    word = struct.pack('<i', o)
    hits = []
    start = 0
    while True:
        k = av.find(word, start)
        if k < 0:
            break
        if k != o:
            hits.append(k)
        start = k + 1
        if len(hits) > 40:
            break
    print('      appears as a 4-byte LE literal %d time(s)%s' % (
        len(hits), (' e.g. 0x%08x' % hits[0]) if hits else ''))
print()
print('  NOTE: a raw address match is only suggestive - Sony code normally')
print('  stores (string - pc) and adds pc back. Confirm by disassembly before')
print('  treating any of this as a live reference.')
