"""Which of the two av-cam candidates is the shipped one?

Evidence so far:
  raw flash capture (nflasha3_system.bin @0x14000)
    == dumps/av-cam.bin.bak  (md5 cdcae9d4...)
    == fw/av-cam.bin         (md5 cdcae9d4...)
  dumps/av-cam.bin          (md5 d1a04a3a...)  differs from those in 18 bytes

So three artefacts agree and one is the outlier. To decide whether the 18
bytes are a benign build stamp or an injected change, compare the same
offsets against Sony's own signed V2.03 av-cam.bin.
"""
import glob
import hashlib
import re
from pathlib import Path

N = 17_289_388
GROUPS = [(0x000aa15a, 4), (0x000c474a, 4), (0x0086e006, 10)]
D = Path(r'D:\02_Development_And_Projects\pmca-re\dumps')


def stamp(b, label):
    print('  %-30s' % label, end='')
    for off, ln in GROUPS:
        print(' |%s' % b[off:off + ln].hex(' '), end='')
    print()


print('=== the 18 disputed bytes, by artefact ===')
print('  %-30s %-13s %-13s %-31s' % ('', '0xaa15a[4]', '0xc474a[4]', '0x86e006[10]'))
cands = {
    'raw flash capture': (D / 'nflasha3_system.bin').read_bytes()[0x14000:0x14000 + N],
    'dumps/av-cam.bin': (D / 'av-cam.bin').read_bytes(),
    'dumps/av-cam.bin.bak': (D / 'av-cam.bin.bak').read_bytes(),
}
fw = Path(r'D:\02_Development_And_Projects\pmca-re\fw\av-cam.bin')
if fw.exists():
    cands['fw/av-cam.bin'] = fw.read_bytes()
for k, v in cands.items():
    stamp(v, k)
print()

# --- find Sony's own signed V2.03 av-cam.bin, if we have it --------------
print('=== hunting for an official Sony av-cam.bin (different build) ===')
pats = [r'**/av-cam*.bin', r'**/FirmwareData*.dat', r'**/F:\RE_DUMP\*.img']
found = []
for pat in pats[:2]:
    for p in glob.glob(r'D:\02_Development_And_Projects\**\%s' % pat.split('**/')[1],
                       recursive=True):
        try:
            sz = Path(p).stat().st_size
        except OSError:
            continue
        found.append((p, sz))
seen = set()
for p, sz in sorted(set(found)):
    if p in seen:
        continue
    seen.add(p)
    if sz == N:
        print('  %-72s %d B  <-- same size' % (p[-72:], sz))
    elif 'dat' in p.lower() or sz > 50_000_000:
        print('  %-72s %d B' % (p[-72:], sz))
print()

# --- do the disputed regions look like a stamp? --------------------------
print('=== decoding 0x86e006 as a build stamp ===')
for k, v in cands.items():
    r = v[0x86e000:0x86e020]
    print('  %-30s %s' % (k, r.hex(' ')))
print()
b = cands['raw flash capture']
print('  raw capture 0x86e000..0x86e01f is all-zero:',
      set(b[0x86e000:0x86e020]) == {0})
print('  av-cam.bin  0x86e000..0x86e01f is all-zero:',
      set(cands['dumps/av-cam.bin'][0x86e000:0x86e020]) == {0})
print()
print('  if the flash capture is blank here and the file is not, the file was')
print('  stamped by a writer, not hand-edited -- a hand edit would not')
print('  conjure a consistent date/time pair 15 KB from the end.')
