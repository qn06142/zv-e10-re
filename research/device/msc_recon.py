#!/usr/bin/env python3
"""Scan msc_dump.bin for anything firmware/service-mode related.

The dump is the 29MB user partition, but we check thoroughly anyway:
  - ASCII/UTF-16 strings (keywords: service, debug, uart, jtag, boot, sony,
    pmap, pmca, unlock, recovery, firmware, 0x98, SCSI vendor, model IDs)
  - Common firmware magic (u-boot, ELF, ARM vectors, 'SONY' model strings)
  - Entropy / repetitive regions (firmware blobs are usually high-entropy)
  - The two .IND control files (BLTINMEM.IND, VOLUMEID.IND) contents
  - Where the photo/JPEG data ends (is there a tail region after the files?)
"""
import re, struct, os

PATH = r'C:\Users\Minhsnguhoa\pmca-re\msc_dump.bin'
data = open(PATH, 'rb').read()
N = len(data)
print('size: %d (%.2f MB)' % (N, N/1e6))

# --- strings ---
def strings(b, minlen=6):
    pat = re.compile(rb'[\x20-\x7e]{%d,}' % minlen)
    return pat.findall(b)
asc = strings(data)
print('\n[ASCII strings >=6]: %d' % len(asc))

kw = [b'service', b'Service', b'SERVICE', b'debug', b'DEBUG', b'uart', b'UART',
      b'JTAG', b'jtag', b'boot', b'BOOT', b'uboot', b'U-Boot', b'Uboot',
      b'firmware', b'FIRMWARE', b'firm', b'unlock', b'UNLOCK', b'recovery',
      b'RECOVERY', b'pmca', b'PMCA', b'PMCA', b'0x98', b'0x980', b'vendor',
      b'VENDOR', b'SCSI', b'sony', b'SONY', b'DSC', b'diag', b'DIAG',
      b'console', b'Console', b'loader', b'LOADER', b'rom', b'ROM', b'0xE0',
      b'serial', b'SERIAL', b'baud', b'BAUD', b'root', b'ROOT', b'shell',
      b'SHELL', b'cmd', b'CMD', b'mode', b'MODE', b'test', b'TEST', b'calib',
      b'CALIB', b'adjust', b'ADJUST']
hits = {}
for k in kw:
    c = data.count(k)
    if c:
        hits[k] = c
if hits:
    print('[keyword hits]')
    for k, v in sorted(hits.items(), key=lambda x: -x[1]):
        print('   %-12s %d' % (k.decode('latin1', 'replace'), v))
else:
    print('[keyword hits] none')

# UTF-16LE strings (firmware sometimes stores wide strings)
u16 = re.findall(rb'(?:[\x20-\x7e]\x00){6,}', data)
print('\n[UTF-16LE strings >=6]: %d' % len(u16))
for s in u16[:15]:
    print('   ', s.decode('utf-16-le', 'replace'))

# --- firmware magic ---
print('\n[firmware magic scan]')
magics = {
    b'\x7fELF': 'ELF',
    b'UBOOT': 'U-Boot string',
    b'\x18\x28\x6e\x01': 'ARM32 exception vec (approx)',
    b'SONY': 'SONY',
    b'PMCA': 'PMCA',
}
for m, name in magics.items():
    c = data.count(m)
    if c:
        print('   %-10s x%d' % (name, c))

# --- the .IND control files (usually at start of FAT) ---
print('\n[.IND control files]')
for name in [b'BLTINMEM.IND', b'VOLUMEID.IND']:
    i = data.find(name)
    if i >= 0:
        # the file is 0 bytes usually; just note location + surrounding bytes
        print('   %s found at 0x%X; nearby: %r' % (name.decode(), i, data[i-16:i+48]))

# --- entropy of 1MB chunks: firmware blobs are high-entropy ---
def entropy(b):
    import math
    from collections import Counter
    c = Counter(b); n = len(b)
    return -sum((v/n)*math.log2(v/n) for v in c.values() if v)

print('\n[entropy per 1MB chunk (8.0 = max/random; low = repetitive/zeros)]')
step = 1024*1024
for off in range(0, N, step):
    chunk = data[off:off+step]
    if not chunk: break
    e = entropy(chunk)
    flag = '  <-- high (possible blob)' if e > 7.5 else ''
    print('   0x%08X-0x%08X  entropy=%.2f%s' % (off, off+len(chunk), e, flag))

# --- where does the real data end? find last non-zero / last JPEG ---
last_nz = N - 1 - next((i for i, b in enumerate(reversed(data)) if b), N)
print('\n[last non-zero byte at 0x%X (%d); device size 0x%X]' % (last_nz, last_nz, N))
# is there a tail of zero/FF after the data?
tail = data[last_nz+1:]
print('   tail after last data: %d bytes; all-zero=%s all-FF=%s'
      % (len(tail), tail == b'\x00'*len(tail), tail == b'\xff'*len(tail)))
