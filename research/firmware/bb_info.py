import struct
from pathlib import Path

for n in ('busybox-armhf', 'busybox-armel'):
    p = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camtools') / n
    b = p.read_bytes()
    e_flags = struct.unpack_from('<I', b, 36)[0]
    e_entry = struct.unpack_from('<I', b, 24)[0]
    hard = bool(e_flags & 0x400)
    print('%-15s %8d B  e_flags=0x%08x  EABI_ver=%d  %s-float  entry=0x%08x' % (
        n, len(b), e_flags, (e_flags >> 24) & 0xFF, 'hard' if hard else 'soft', e_entry))
    # a couple of sanity strings that prove it is really busybox
    for s in (b'BusyBox v', b'Currently defined functions:', b'Usage: busybox'):
        if s in b:
            print('    contains %r' % s.decode())
