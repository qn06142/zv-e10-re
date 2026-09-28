"""What is style_cmn.uxc, and does it speak the same id language as the palette?

This is now the right next question, because we have ground truth.  The boot
proved that 0x40xx ids in color_cmn.uxc are the currency the engine uses to
resolve colours.  So the useful question is no longer "is the format guessed"
but "what else is expressed in that currency, and what does each file control".

style_cmn.uxc (1,888 B) is the obvious candidate.  Earlier I noted it has
w2=0xc03c rather than color_cmn's 0x4023, so it is a *different* table, not a
second palette.  That makes it something more interesting than a palette: a
style or attribute set that screens reference.

Three questions:

Q1  Does style_cmn.uxc contain 0x40xx ids?  If yes, styles reference palette
    colours by id, which means style_cmn is a second lever on the same colours
    and the two files interact.  That is the interaction worth understanding
    before touching either.

Q2  Is its body a fixed stride like the palette's, or something else?  Compare
    its length against candidate strides rather than assuming 8.

Q3  What are the uxa/uxb tables doing?  style.uxb is 540 B and lang.uxb is
    2,896 B, both with u32 offset tables at 0x10.  If they are directories
    rather than records, they are how the engine finds the _cmn variants, which
    matters for knowing whether renaming or adding a file is possible.

Deliberately not guessing: anything that depends on a stride is tested against
the file length, and the answer is reported per hypothesis rather than picked.
"""
import re
import struct
import tarfile
from collections import Counter
from pathlib import Path

TGZ_CANDIDATES = [
    Path(r'F:\RE_DUMP\TREES\usr_share.tgz'),   # the card, when it is attached
    Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz'),
]


def pick():
    for p in TGZ_CANDIDATES:
        if p.exists():
            try:
                with p.open('rb') as f:
                    f.read(2)
                return p
            except OSError:
                continue
    raise SystemExit('no readable usr/share archive; tried:\n  %s'
                     % '\n  '.join(str(p) for p in TGZ_CANDIDATES))


def load(names=None):
    t = tarfile.open(pick())
    out = {}
    for m in t.getmembers():
        if not m.isfile():
            continue
        if names and m.name.split('/')[-1] not in names:
            continue
        out[m.name.split('/')[-1]] = t.extractfile(m).read()
    return out


def hdr(b):
    return dict(magic=b[:3].decode('latin1'),
                ver=b[3],
                stream=struct.unpack_from('<H', b, 8)[0],
                w1=struct.unpack_from('<H', b, 10)[0],
                w2=struct.unpack_from('<H', b, 12)[0])


def dump(b, lo, hi, width=16):
    for o in range(lo, min(hi, len(b)), width):
        ch = b[o:o + width]
        txt = ''.join(chr(c) if 32 <= c < 127 else '.' for c in ch)
        print('    %04x  %-47s |%s|'
              % (o, ' '.join('%02x' % c for c in ch), txt))


def palette_ids(cb):
    hw = struct.unpack_from('<H', cb, 12)[0]
    base = hw - 0x23
    return base, {v for v in range(base, hw)}


def q1_style(d, ids):
    print('=' * 74)
    print('Q1  does style_cmn.uxc speak the palette id language?')
    print('=' * 74)
    sc = d['style_cmn.uxc']
    h = hdr(sc)
    print('  style_cmn.uxc  %d bytes  %s' % (len(sc), h))
    print()
    hits = {}
    for o in range(0, len(sc) - 1):
        v = struct.unpack_from('<H', sc, o)[0]
        if v in ids:
            hits.setdefault(v, []).append(o)
    if hits:
        print('  %d distinct palette ids, %d occurrences:'
              % (len(hits), sum(len(v) for v in hits.values())))
        for v in sorted(hits):
            print('    id 0x%04x  %s' % (v, ' '.join('0x%04x' % o
                                                   for o in hits[v][:8])))
    else:
        print('  NO palette ids found.')
    print()
    print('  contrast: color_cmn.uxc has them at every record position, and the')
    print('  boot proved they resolve. So a hit here is meaningful, and a')
    print('  non-hit means style_cmn uses some other id space.')
    return hits


def q2_stride(d):
    print()
    print('=' * 74)
    print('Q2  what is the record shape? test strides, do not assume')
    print('=' * 74)
    for name in ('style_cmn.uxc', 'color_cmn.uxc'):
        b = d[name]
        print()
        print('  --- %s  %d bytes ---' % (name, len(b)))
        body = len(b) - 0x58
        print('    body from 0x58 = %d bytes' % body)
        for s in (4, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 64):
            if body % s == 0 and body // s >= 4:
                print('      stride %2d divides evenly: %2d records'
                      % (s, body // s))
    print()
    print('  style_cmn.uxc head:')
    dump(d['style_cmn.uxc'], 0, 0x60)
    print()
    print('  style_cmn.uxc body from 0x58:')
    dump(d['style_cmn.uxc'], 0x58, 0xA0)


def q3_uxb(d):
    print()
    print('=' * 74)
    print('Q3  style.uxb and lang.uxb: directories or records?')
    print('=' * 74)
    for name in ('style.uxb', 'lang.uxb'):
        b = d[name]
        h = hdr(b)
        print()
        print('  --- %s  %d bytes  %s' % (name, len(b), h))
        dump(b, 0, 0x50)
        nw = (len(b) - 0x10) // 4
        offs = [struct.unpack_from('<I', b, 0x10 + 4 * i)[0] for i in range(nw)]
        sane = [o for o in offs if o < len(b)]
        print('    u32 from 0x10: %d words, %d in range' % (len(offs), len(sane)))
        print('    first 14: %s' % ' '.join('%08x' % o for o in offs[:14]))
        runs = [(m.start(), m.group().decode('latin1'))
                for m in re.finditer(rb'[\x20-\x7e]{4,}', b)]
        print('    %d printable runs' % len(runs))
        for o, t in runs[:10]:
            print('      0x%04x  %s' % (o, t[:60]))


def main():
    d = load({'color_cmn.uxc', 'style_cmn.uxc', 'style.uxb', 'lang.uxb',
              'lang_cmn.uxc', 'global.xdb'})
    base, ids = palette_ids(d['color_cmn.uxc'])
    print('palette ids 0x%04x..0x%04x (%d)' % (base, base + 0x22, len(ids)))
    print()
    q1_style(d, ids)
    q2_stride(d)
    q3_uxb(d)


if __name__ == '__main__':
    main()
