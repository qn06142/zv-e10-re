"""Inventory usr.tgz, tolerating the truncated gzip tail.

The card's usr.tgz is 91,820,032 bytes and its md5 matches MD5SUMS.txt exactly
(ddbb62adef9fc94284cbefa43637ad73), so the transfer is good -- the archive
itself was written truncated, and python's tarfile raises EOFError while seeking
to enumerate members.

That still leaves most of the file readable: gzip is a stream, and members
written before the cut are intact.  So instead of tarfile, read the tar stream
by hand, stopping cleanly at the first damaged block rather than aborting.

This matters because the open question is where the uxc parser lives.  /usr/bin
has no candidate -- its 48 files are tools, the largest being bsa_server (BTS).
etc/procs.txt shows 60+ threads named liro-kliro_* and a process map mentioned
uxengine_res2, so the engine is a userspace binary somewhere under /usr, and the
full tree is the only place it can be.

A hand-rolled tar reader is small and has no seeking requirement:

    header  512 bytes, name at 0, size at 124 (octal), typeflag at 156
    payload padded to a 512 multiple
    two zero blocks terminate

Reading sequentially and stopping on a short read or an implausible size gets
every member that was actually written.

The goal is a list of ELF files by size, then a search of the big ones for
palette-id immediates -- with a control-id null model, because a two-byte value
in a large binary produces hits by the thousand and means nothing alone.
"""
import gzip
import struct
from collections import Counter
from pathlib import Path

USR = Path(r'F:\RE_DUMP\usr.tgz')
BLOCK = 512
ELF = b'\x7fELF'


def parse_tar_stream(fh):
    """Yield (name, size, offset) for each member, stopping at the damage."""
    good = 0
    try:
        while True:
            hdr = fh.read(BLOCK)
            if len(hdr) < BLOCK:
                print('  stopped: short header at member %d' % good)
                return
            if hdr == b'\x00' * BLOCK:
                print('  clean end-of-archive at member %d' % good)
                return
            name = hdr[0:100].rstrip(b'\x00').decode('latin1', 'replace')
            try:
                size = int(hdr[124:136].rstrip(b'\x00 ').decode('latin1') or '0', 8)
            except ValueError:
                print('  stopped: unparsable size at member %d (%r)' % (good, name))
                return
            typ = hdr[156:157]
            if size < 0 or size > 200 * 1024 * 1024:
                print('  stopped: implausible size %d at member %d (%r)'
                      % (size, good, name))
                return
            yield name, size, typ
            good += 1
            pad = (size + BLOCK - 1) // BLOCK * BLOCK
            left = pad
            while left > 0:
                c = fh.read(min(left, 1 << 20))
                if not c:
                    print('  stopped: truncated payload of %s at member %d'
                          % (name, good))
                    return
                left -= len(c)
    except (EOFError, OSError) as e:
        print('  stopped on stream error after %d members: %s' % (good, e))
        return


def main():
    print('=== %s ===' % USR)
    print()
    with gzip.open(USR, 'rb') as fh:
        members = list(parse_tar_stream(fh))
    print('  %d members recovered' % len(members))
    print()
    total = sum(s for _n, s, _t in members)
    print('  %d MB of payload' % (total / 1048576))
    print()

    print('=== top-level directories ===')
    top = Counter()
    for n, s, _t in members:
        p = n.lstrip('./').split('/')
        top['/'.join(p[:2]) if len(p) > 2 else (p[0] if p else '.')] += 1
    for d, c in top.most_common(30):
        print('  %-32s %5d' % (d, c))
    print()

    print('=== largest 40 members ===')
    for n, s, t in sorted(members, key=lambda x: -x[1])[:40]:
        kind = {b'0': 'file', b'5': 'dir', b'2': 'link'}.get(t, repr(t))
        print('  %10d  %-46s %s' % (s, n[:46], kind))
    print()

    # find ELFs by reading just their first 4 bytes
    print('=== ELF files (magic \x7fELF) ===')
    elfs = []
    with gzip.open(USR, 'rb') as fh:
        # re-walk and record payload offsets by re-reading sequentially
        offset = 0
        try:
            while True:
                hdr = fh.read(BLOCK)
                if len(hdr) < BLOCK or hdr == b'\x00' * BLOCK:
                    break
                name = hdr[0:100].rstrip(b'\x00').decode('latin1', 'replace')
                try:
                    size = int(hdr[124:136].rstrip(b'\x00 ').decode('latin1') or '0', 8)
                except ValueError:
                    break
                if size < 0 or size > 200 * 1024 * 1024:
                    break
                if size >= 4:
                    magic = fh.read(4)
                    if magic == ELF:
                        elfs.append((name, size))
                    fh.read(size - 4)
                else:
                    fh.read(size)
                pad = (size + BLOCK - 1) // BLOCK * BLOCK - size
                if pad:
                    fh.read(pad)
        except (EOFError, OSError):
            pass
    for n, s in sorted(elfs, key=lambda x: -x[1])[:40]:
        print('  %10d  %s' % (s, n))
    print('  (%d ELFs)' % len(elfs))
    print()
    print('  The UI engine is not in /usr/bin (48 tool files, largest')
    print('  bsa_server 4.8 MB = Bluetooth). If it is under /usr it shows up')
    print('  in this list by size.')


if __name__ == '__main__':
    main()
