"""Stage the static ARM busyboxes onto the SD card, with readback verification
(same discipline as staging the firmware images: copy, then re-read and hash).
"""
import hashlib
import shutil
from pathlib import Path

CARD = Path(r'F:\tools')
CARD.mkdir(parents=True, exist_ok=True)
SRC = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camtools')

FILES = ['busybox-armhf', 'busybox-armel']


def md5(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 22), b''):
            h.update(c)
    return h.hexdigest()


print('=== source ===')
for n in FILES:
    p = SRC / n
    print('  %-16s %9d B  md5 %s' % (n, p.stat().st_size, md5(p)))

print()
print('=== copying to %s ===' % CARD)
for n in FILES:
    shutil.copyfile(SRC / n, CARD / n)
    print('  copied %s' % n)

print()
print('=== readback from the card (catches FAT32 truncation / unflushed writes) ===')
ok = True
for n in FILES:
    a, b = SRC / n, CARD / n
    sa, sb = a.stat().st_size, b.stat().st_size
    ha, hb = md5(a), md5(b)
    same = (sa == sb) and (ha == hb)
    ok = ok and same
    print('  %-16s card %9d B  md5 %s  %s' % (n, sb, hb, 'OK' if same else '*** MISMATCH ***'))

# a tiny note so the binaries are not mistaken for camera files
(CARD / 'README.txt').write_text(
    'Static ARM busybox, staged for use on the ZV-E10 (armv7l).\n\n'
    '  busybox-armhf  Debian bookworm busybox-static 1.35.0, ARMv7 hard-float\n'
    '  busybox-armel  same, soft-float (fallback if hard-float faults)\n\n'
    'The camera ships a minimal busybox 1.34.1 with no diff, awk, tr, od,\n'
    'printf, stat or head.  These are statically linked, so no libraries are\n'
    'needed - copy to /tmp and chmod +x, then run directly:\n\n'
    '  /tmp/busybox-armhf --list\n'
    '  /tmp/busybox-armhf diff a b\n'
    '  /tmp/busybox-armhf awk ...\n\n'
    'Check the arch first:  cat /proc/cpuinfo | grep -i vfp\n'
)

print()
print('=== card tools/ ===')
for p in sorted(CARD.iterdir()):
    print('  %-18s %9d B' % (p.name, p.stat().st_size))
print()
print('STAGING %s' % ('OK' if ok else 'FAILED'))
