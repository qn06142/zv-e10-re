"""Parse the ORIL container header in av-cam.bin to find the load segments.

This decides the cave question: a code cave is only usable if it is MAPPED
and EXECUTABLE.  A 4.9 MB run of zeros at 0xAEDC95 is useless if the
container never maps that file range into memory.
"""
import struct
from pathlib import Path

av = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
N = len(av)

print('=== first 0x100 bytes of the ORIL container ===')
for off in range(0, 0x100, 16):
    row = av[off:off + 16]
    txt = ''.join(chr(b) if 32 <= b < 127 else '.' for b in row)
    print('  0x%04x  %s  %s' % (off, row.hex(' '), txt))
print()

print('=== plausible header fields ===')
for off, fmt, name in ((0x00, '<I', 'word0'), (0x04, '<4s', 'magic'),
                       (0x08, '<I', 'word2'), (0x0c, '<I', 'word3'),
                       (0x10, '<I', 'word4'), (0x14, '<I', 'word5'),
                       (0x18, '<I', 'word6'), (0x1c, '<I', 'word7'),
                       (0x20, '<I', 'word8'), (0x24, '<I', 'word9'),
                       (0x28, '<I', 'word10'), (0x2c, '<I', 'word11')):
    v = struct.unpack_from(fmt, av, off)[0]
    extra = ''
    if name == 'magic':
        extra = repr(v)
    elif v and v < N:
        extra = '(plausible size/offset: %.2f MB)' % (v / 1e6)
    print('  0x%02x %-7s = 0x%08x %s' % (off, name, v if isinstance(v, int) else 0, extra))
print()

print('=== look for a segment table: (fileoff, filesize, memaddr) triples in first 0x400 ===')
cands = []
for off in range(0, 0x400, 4):
    fo, fs, ma = struct.unpack_from('<III', av, off)
    if 0 < fo < N and 0 < fs <= N - fo and fs > 0x1000:
        if ma < 0x40000000 and (ma & 0xfff) == 0:
            cands.append((off, fo, fs, ma))
for off, fo, fs, ma in cands[:24]:
    print('  @0x%04x  fileoff=0x%08x  size=0x%08x (%.2f MB)  memaddr=0x%08x'
          % (off, fo, fs, fs / 1e6, ma))
print('  (%d plausible triples)' % len(cands))
print()

print('=== where does real content end? ===')
# last non-zero byte
last = N - 1
while last > 0 and av[last] == 0:
    last -= 1
print('  last non-zero byte at 0x%08x (%.2f MB)' % (last, last / 1e6))
print('  file size                0x%08x (%.2f MB)' % (N, N / 1e6))
print('  trailing zeros           %d bytes (%.2f MB)' % (N - 1 - last, (N - 1 - last) / 1e6))
print()
print('  the 4.9 MB zero run at 0xAEDC95 spans to 0x%08x' % (0xAEDC95 + 4901483))
print('  -> it sits between real content and the end of file, which is the')
print('     signature of container padding, not of unmapped code space.')
