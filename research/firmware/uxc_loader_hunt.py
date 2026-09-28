"""Locate the uxc/uxb/uxa resource loader inside the dumped firmware.

This is the offline attack on the two questions that gate the palette plan.

Q2  Does anything actually consume color_cmn.uxc's colour ids?
    If the uxc parser and the palette consumer are in the firmware, the
    disassembly will show whether the 0x4000-range ids are used as indices
    into a table (confirming the decode) or ignored.  A negative here is
    decisive and would save a camera session.

Q5  Where does the engine LOOK for these files?
    The engine opens resources by absolute path (global.xdb stores 15
    /usr/share/app/... paths).  If the loader builds that path by
    concatenating a base directory string, the base string sits in .rodata
    and the search-path question -- does an SD card override the root? -- can
    be answered by reading the loader rather than by experiment.

Targets, all local, all already dumped:
  dumps/av-cam.bin.bak    17.3 MB   the app that draws the UI (vanilla)
  dumps/fdat_decrypted.bin 371 MB  whole firmware

Search strategy: the container magics are 3-byte ASCII ('uxc','uxb','uxa'),
and the format version byte 0x07 with stream 0x0008 / 0x0009 is a tight
signature.  The file names themselves (color_cmn.uxc, global.xdb) are the
strongest anchors -- a loader must name the files it loads.

Arm caveat, learned the hard way on av-cam.bin: string references in this
Thumb code are PC-relative (thumb.pcrel_strrefs), and symbol/function
addresses carry the Thumb bit.  Plain byte search for the literal is still
valid and is the cheap first pass.
"""
import re
import struct
from pathlib import Path

ROOT = Path(r'D:\02_Development_And_Projects\pmca-re\dumps')

# strong anchors: names a loader must contain
NAMES = [
    b'color_cmn.uxc', b'color_cmn', b'style_cmn.uxc', b'style.uxb',
    b'global.xdb', b'lang.uxb', b'fontlist.dat', b'viewBaseMenu',
    b'.uxc', b'.uxb', b'.uxa', b'/usr/share/app',
]

# container magic + version signature
def sig_uxc(b):
    return b[:3] == b'uxc' and b[3] == 0x07 and b[8:10] == b'\x08\x00'

def sig_uxb(b):
    return b[:3] == b'uxb' and b[3] == 0x07 and b[8:10] == b'\x09\x00'

def sig_uxa(b):
    return b[:3] == b'uxa' and b[3] == 0x07 and b[8:10] == b'\x09\x00'


def scan(buf, path, is_elf_like):
    print('=' * 74)
    print('=== %s  (%d bytes) ===' % (path.name, len(buf)))
    print('=' * 74)

    print('-- named-resource anchors --')
    for n in NAMES:
        offs = []
        start = 0
        while True:
            i = buf.find(n, start)
            if i < 0:
                break
            offs.append(i)
            start = i + 1
            if len(offs) >= 12:
                break
        if offs:
            print('  %-16s %d hit(s)  %s' % (
                n.decode('latin1'), len(offs),
                ' '.join('0x%08x' % o for o in offs[:8])))

    # container signatures at plausible alignment
    for name, sig in (('uxc', sig_uxc), ('uxb', sig_uxb), ('uxa', sig_uxa)):
        hits = []
        for m in re.finditer(re.escape(name.encode()), buf):
            o = m.start()
            if o + 16 <= len(buf) and sig(buf[o:o + 16]):
                # how big is the record it claims?
                ln = struct.unpack_from('<H', buf, o + 10)[0]
                hits.append((o, ln))
            if len(hits) >= 8:
                break
        if hits:
            print('-- %s container signatures: %d --' % (name, len(hits)))
            for o, ln in hits:
                print('     @0x%08x  hdrw=0x%04x' % (o, ln))

    # the palette id high-water 0x4023 as a u32 or u16 constant
    for pat, desc in ((b'\x23\x40\x00\x00', 'u32 0x4023'),
                      (b'\x23\x40', 'u16 0x4023'),
                      (b'\x00\x40\x00\x00', 'u32 0x4000'),
                      (b'\x3a\x09', 'u16 0x093a (palette const LE)')):
        c = buf.count(pat)
        if c:
            print('  const %-24s %d occurrence(s)' % (desc, c))


def main():
    avcam = (ROOT / 'av-cam.bin.bak').read_bytes()
    scan(avcam, ROOT / 'av-cam.bin.bak', True)
    print()
    big = (ROOT / 'fdat_decrypted.bin').read_bytes()
    scan(big, ROOT / 'fdat_decrypted.bin', True)


if __name__ == '__main__':
    main()
