"""Fetch a prebuilt STATIC ARM busybox to bundle on the SD card.

No ARM cross-compiler on this box, so take Debian's busybox-static armhf
rather than building one.  A .deb is an `ar` archive containing
data.tar.{xz,zst}; parse it by hand rather than shelling out to dpkg-deb.
"""
import io
import lzma
import struct
import sys
import tarfile
import urllib.request
from pathlib import Path

OUT = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camtools')
OUT.mkdir(parents=True, exist_ok=True)

DEBS = [
    ('armhf', 'http://deb.debian.org/debian/pool/main/b/busybox/busybox-static_1.35.0-4+deb12u1+b1_armhf.deb'),
    ('armel', 'http://deb.debian.org/debian/pool/main/b/busybox/busybox-static_1.35.0-4+deb12u1+b1_armel.deb'),
]


def ar_members(blob):
    """Parse a .deb (ar archive).  Yields (name, data)."""
    if blob[:8] != b'!<arch>\n':
        raise ValueError('not an ar archive: %r' % blob[:8])
    off = 8
    while off + 60 <= len(blob):
        hdr = blob[off:off + 60]
        name = hdr[0:16].decode('ascii', 'replace').strip()
        try:
            size = int(hdr[48:58].decode('ascii').strip())
        except ValueError:
            break
        data = blob[off + 60:off + 60 + size]
        yield name.rstrip('/'), data
        off += 60 + size + (size & 1)


def pick_data_tar(members):
    for name, data in members:
        if name.startswith('data.tar'):
            return name, data
    raise ValueError('no data.tar in the deb')


def extract_deb(blob):
    name, data = pick_data_tar(list(ar_members(blob)))
    print('  data member: %s (%d bytes)' % (name, len(data)))
    if name.endswith('.xz'):
        data = lzma.decompress(data)
    elif name.endswith('.gz'):
        import gzip
        data = gzip.decompress(data)
    elif name.endswith('.zst'):
        raise SystemExit('data.tar.zst needs python-zstandard; pick an older .deb')
    elif name.endswith('.tar'):
        pass
    else:
        raise SystemExit('unknown compression: %s' % name)
    tf = tarfile.open(fileobj=io.BytesIO(data))
    return tf


def describe_elf(b, label):
    """Confirm ARM, and whether it is statically linked."""
    if b[:4] != b'\x7fELF':
        return 'not an ELF'
    cls = {1: '32-bit', 2: '64-bit'}.get(b[4], '?')
    endian = {1: 'little', 2: 'big'}.get(b[5], '?')
    e_type, e_machine = struct.unpack_from('<HH', b, 16)
    machines = {40: 'EM_ARM', 183: 'EM_AARCH64', 3: 'EM_386', 62: 'EM_X86_64'}
    # walk program headers looking for PT_INTERP (3)
    e_phoff = struct.unpack_from('<I', b, 28)[0]
    e_phentsize, e_phnum = struct.unpack_from('<HH', b, 42)
    interp = False
    for k in range(e_phnum):
        off = e_phoff + k * e_phentsize
        if off + 4 > len(b):
            break
        p_type = struct.unpack_from('<I', b, off)[0]
        if p_type == 3:
            interp = True
    return ('%s %s-endian  %s  type=%d  %s' % (
        cls, endian, machines.get(e_machine, 'machine=%d' % e_machine),
        e_type, 'DYNAMIC (needs libs)' if interp else 'STATIC (no PT_INTERP)'))


for arch, url in DEBS:
    print('=== %s ===' % url.rsplit('/', 1)[-1])
    try:
        with urllib.request.urlopen(url, timeout=90) as r:
            blob = r.read()
    except Exception as e:
        print('  download failed: %s' % e)
        continue
    print('  downloaded %d bytes' % len(blob))
    tf = extract_deb(blob)
    want = [m for m in tf.getmembers()
            if m.isfile() and m.name.lstrip('./') in ('bin/busybox', 'bin/busybox.static')]
    if not want:
        names = [m.name for m in tf.getmembers() if m.isfile()][:20]
        print('  bin/busybox not found; first files: %s' % names)
        continue
    for m in want:
        data = tf.extractfile(m).read()
        dest = OUT / ('busybox-%s' % arch)
        dest.write_bytes(data)
        dest.chmod(0o755)
        print('  extracted %s -> %s' % (m.name, dest))
        print('    %d bytes' % len(data))
        print('    %s' % describe_elf(data, arch))
