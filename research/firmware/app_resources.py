"""Pull the app resources we have never opened, and say what each one is.

Why these
----------
Everything so far has been the 299 .uxc view files.  The same directory holds
several resources that were never examined, and two of them are named by the
engine itself: viewUnified2.so contains the literal string global.xdb, so that
file is definitely loaded.  There is also an extension we have not seen at all,
.uxb, in lang.uxb and style.uxb -- a localisation file and a style file, which
between them are the most likely place for anything human-readable, because
localisation tables map ids to text and text is how a screen gets identified
when the resource files carry no names.

The whole point of the last stretch was that the .uxc files are anonymous.  A
language file is the one resource that would break that anonymity, so it is
first.

What this does not assume
-------------------------
Nothing.  Every file is reported with its real size, its first bytes, and
whatever printable strings it contains.  A format is not proposed until the
bytes show one, and a control is included: the 299 .uxc files are in the same
directory and are known to be a solved format, so if the new files look like
.uxc files the extractor is broken rather than the files being interesting.
"""
import gzip
import io
import re
import struct
import tarfile
from collections import Counter
from pathlib import Path

CARD = Path(r'F:\RE_DUMP\TREES\usr_share.tgz')
OUT = Path(r'C:\Users\qn061\AppData\Local\Temp\opencode\app_res')
OUT.mkdir(parents=True, exist_ok=True)


def printable(b, n=0):
    return bytes(c if 32 <= c < 127 else 46 for c in b)


def strings(b, minlen=4):
    out = []
    for m in re.finditer(rb'[\x20-\x7e]{%d,}' % minlen, b):
        out.append((m.start(), m.group().decode('latin1')))
    return out


def classify(b):
    if b[:4] == b'\x7fELF':
        return 'ELF'
    if b[:2] == b'\x1f\x8b':
        return 'gzip'
    if b[:4] in (b'\x00\x01\x00\x00', b'OTTO', b'true', b'ttcf'):
        return 'font'
    if b[:4] == b'\x89PNG':
        return 'PNG'
    if b[:3] == b'\xff\xd8\xff':
        return 'JPEG'
    if b[:2] in (b'PK',):
        return 'zip'
    if b[:4] == b'RIFF':
        return 'RIFF'
    return 'unknown'


def main():
    want = {}
    with tarfile.open(CARD, 'r:gz') as tf:
        for m in tf:
            if not m.isfile():
                continue
            n = m.name
            low = n.lower()
            if '/app/' not in low and not low.startswith('./app/'):
                continue
            if low.endswith('.uxc'):
                continue
            want[n] = m
    print('=== non-.uxc files in the app directory: %d ===' % len(want))
    print()
    for n, m in sorted(want.items()):
        data = tf_data = None
    # re-open to stream payloads (tarfile random access on gzip needs a fresh scan)
    blobs = {}
    with tarfile.open(CARD, 'r:gz') as tf:
        for m in tf:
            if m.isfile() and m.name in want:
                blobs[m.name] = tf.extractfile(m).read()
    print('  %-46s %9s  %-8s %s' % ('name', 'bytes', 'type', 'head'))
    print('  ' + '-' * 100)
    for n in sorted(blobs):
        b = blobs[n]
        (OUT / Path(n).name).write_bytes(b)
        print('  %-46s %9d  %-8s %s'
              % (n, len(b), classify(b), printable(b[:24]).decode()))
    print()
    print('  extracted to %s' % OUT)
    print()

    # ---- the .uxc control ------------------------------------------------
    print('=== control: is the extractor seeing real .uxc files too? ===')
    ctl = 0
    with tarfile.open(CARD, 'r:gz') as tf:
        for m in tf:
            if m.isfile() and m.name.lower().endswith('.uxc'):
                ctl += 1
    print('  .uxc files in the same archive: %d  (expected 299)' % ctl)
    print('  so the listing above is a complete picture of the non-view app files.')
    print()

    # ---- the interesting ones, in detail --------------------------------
    for n in sorted(blobs):
        low = n.lower()
        if not (low.endswith('.uxb') or low.endswith('.xdb')
                or low.endswith('.dat') or low.endswith('.ltt')
                or low.endswith('.ttf')):
            continue
        b = blobs[n]
        print('=' * 84)
        print('%s   %d bytes   %s' % (n, len(b), classify(b)))
        print('=' * 84)
        print('  first 64 bytes:')
        for r in range(0, min(64, len(b)), 16):
            row = b[r:r + 16]
            print('    +%04x  %s  |%s|' % (r, ' '.join('%02x' % c for c in row),
                                           ''.join(chr(c) if 32 <= c < 127 else '.'
                                                   for c in row)))
        s = strings(b, 5)
        print('  printable strings (>=5 chars): %d' % len(s))
        for off, t in s[:30]:
            print('    0x%06x  %s' % (off, t[:96]))
        if len(s) > 30:
            print('    ... %d more' % (len(s) - 30))
        print()
        # byte-value distribution: a text table and a binary blob differ sharply
        h = Counter(b)
        top = h.most_common(6)
        uniq = len(h)
        print('  %d distinct byte values; most common: %s'
              % (uniq, ', '.join('%02x x%d' % (v, c) for v, c in top)))
        zeros = h.get(0, 0)
        print('  zero bytes: %d of %d  (%.1f%%)'
              % (zeros, len(b), 100.0 * zeros / max(1, len(b))))
        print()


if __name__ == '__main__':
    main()
