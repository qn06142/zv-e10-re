"""Map osal_id constants to the command names that sit beside them.

Why this replaces reverse engineering
-------------------------------------
`av-cam.bin` was recorded as "encrypted body, hardware secure-core decrypt at
boot", and that is wrong.  Measured over 4 KB blocks: 2,459 of 4,221 are below
6.5 bits/byte and the low-entropy region spans 0x0000000..0x107e000, which is
essentially the whole 16.5 MB file.  `CMD_ID_SDF_EXEC` is at 0x97471a,
`ExecSensCmd` at 0x9500c4, both in the clear.  The high-entropy blocks are
compressed sections, not a cipher.

That matters because the osal_id namespace is then *findable* rather than
hidden.  The one id known to be accepted, 0x00dc0000, occurs twelve times as a
little-endian constant between 0x87b766 and 0x8dd75a, and there are 519 distinct
values in the 0x00dc???? family.  The previous note that "the actual command IDs
live in code, not the string table" was a statement about string extraction
having been tried, not about the data being unavailable.

So: no disassembly.  For each id, take the printable strings within a short
window and report them.  ARM compilers put string literals in literal pools
close to the code that references them, so adjacency carries real information --
and where it does not, that shows up as an empty window rather than as a wrong
answer, which is the failure mode worth having.
"""
import collections
import pathlib
import re
import struct

BIN = pathlib.Path(__file__).resolve().parents[2] / 'fw' / 'av-cam.bin'
PREFIX = 0x00DC0000
WINDOW = 0x400
MIN_STR = 5


def load():
    d = BIN.read_bytes()
    print('av-cam.bin  %d bytes  magic %s' % (len(d), d[:4].hex()))
    return d


def find_family(d):
    """every aligned 32-bit value in the osal_id family, with its offsets"""
    by_id = collections.defaultdict(list)
    for off in range(0, len(d) - 3, 4):
        v = struct.unpack_from('<I', d, off)[0]
        if (v & 0xFFFF0000) == PREFIX:
            by_id[v].append(off)
    return by_id


def nearby_strings(d, off, window=WINDOW):
    lo = max(0, off - window)
    hi = min(len(d), off + window)
    out = []
    for m in re.finditer(rb'[\x20-\x7e]{%d,}' % MIN_STR, d[lo:hi]):
        t = m.group().decode('latin1')
        # keep things that look like identifiers or paths, drop obvious junk
        if not re.search(r'[A-Za-z]{3}', t):
            continue
        out.append((lo + m.start(), t))
    return out


def main():
    d = load()
    by_id = find_family(d)
    print('distinct 0x%08x???? ids: %d   total occurrences: %d'
          % (PREFIX, len(by_id), sum(len(v) for v in by_id.values())))
    print()

    # an id with no strings near any of its occurrences carries no information;
    # count those so the report is not quietly padded with them
    informative = {}
    for v, offs in by_id.items():
        names = collections.Counter()
        for o in offs:
            for _pos, t in nearby_strings(d, o):
                names[t] += 1
        if names:
            informative[v] = names

    print('ids with at least one readable string within %d bytes: %d of %d'
          % (WINDOW, len(informative), len(by_id)))
    print()

    # the interesting ones are those whose neighbourhood names a subsystem
    interesting = []
    for v, names in informative.items():
        joined = ' '.join(names)
        if any(k in joined for k in
               ('Sens', 'Sdf', 'SDF', 'Jpeg', 'Movie', 'Rc', 'Vfx', 'Pin',
                'Cmd', 'CmdId', 'osal', 'Osal', 'Update', 'Fw', 'Setting',
                'Exec', 'Msg', 'Handler')):
            interesting.append((v, names))
    interesting.sort()

    print('=== ids whose neighbourhood names a dispatch family ===')
    for v, names in interesting[:40]:
        top = ', '.join('%s x%d' % (t, c) for t, c in names.most_common(4))
        print('  0x%08x  x%-3d  %s' % (v, len(by_id[v]), top[:120]))
    if len(interesting) > 40:
        print('  ... and %d more' % (len(interesting) - 40))

    print()
    print('=== the known-good id, for calibration ===')
    good = PREFIX
    for o in by_id.get(good, []):
        names = nearby_strings(d, o)
        print('  0x%07x  %s' % (o, ', '.join(t for _p, t in names)[:150]))


if __name__ == '__main__':
    main()
