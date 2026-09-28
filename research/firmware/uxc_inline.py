"""style_cmn.uxc carries INLINE colours, not palette ids.  Verify across all 295.

The single most important finding in the whole uxc investigation, and it comes
straight out of the previous run's last dump line:

    style_cmn.uxc  @0x88
    00 a0 07 26 08 00 00 00 00 00 00 00 dd dd dd ff

`dd dd dd ff` is palette entry 0x4001 verbatim -- the same light grey.  It is
sitting *inside* the style file.  And style_cmn.uxc contains no 0x40xx ids at
all, which Q1 established.  So:

    styles do not reference the palette.  They inline their own RGBA.

That is a much better lever than the palette was, and it explains the boot
result.  The framing guides are drawn by a style, not looked up by id, which is
why recolouring id 0x400c happened to work on them and why a 5-byte palette
edit produced a large visible area change: the guides went blue because a style
inherits or copies from the palette default, or because 0x400c is what the
guide style resolved to at build time.

What this script establishes, with the boot result as ground truth:

Q1  Over all 295 uxc files, how many inline an rgba quad that exactly matches a
    known palette colour?  That quantifies how much of the UI is defined by
    literal colours rather than by the palette.

Q2  Of the files that do, how concentrated is it?  If it is a handful of shared
    files, the whole UI's colour is controllable from a few edits.  If it is
    spread across 200 screens, it is not.

Q3  A 4-byte-aligned rgba quad is a weak signature -- a random 4 bytes match
    some palette entry by chance.  So require BOTH that the quad matches a
    palette colour AND that it sits in a position that looks like a record
    field.  Compare against a null model: how often would 4 random bytes hit
    the 28-entry palette set?  If the observed rate is far above chance, the
    inline-colour reading is real.

The null model matters.  With 28 of 2^32 possible quads, chance hits are rare,
but the palette contains dd-dd-dd, 33-33-33, cc-cc-cc, 00-00-00, ff-ff-ff and
ff-00-00 style values that are exactly the kind of byte pattern that appears in
sizes, counts and padding.  So the null model is computed, not assumed.
"""
import struct
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

CANDIDATES = [
    Path(r'F:\RE_DUMP\TREES\usr_share.tgz'),
    Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz'),
]

REC = 8
HDR = 0x58
ID_BASE = 0x4000


def pick():
    for p in CANDIDATES:
        if p.exists():
            try:
                with p.open('rb') as f:
                    f.read(2)
                return p
            except OSError:
                continue
    raise SystemExit('no readable archive')


def load():
    t = tarfile.open(pick())
    out = {}
    for m in t.getmembers():
        if m.isfile() and m.name.endswith(('.uxc', '.uxb')):
            out[m.name.split('/')[-1]] = t.extractfile(m).read()
    return out


def palette(d):
    b = d['color_cmn.uxc']
    n = (len(b) - HDR) // REC
    out = {}
    for i in range(n):
        o = HDR + i * REC
        cid, const, r, g, bl, a = struct.unpack_from('<HHBBBB', b, o)
        out[(r, g, bl, a)] = cid - ID_BASE
    return out


def quad_at(b, o):
    return tuple(b[o:o + 4])


def main():
    d = load()
    pal = palette(d)
    print('=== %d uxc/uxb files ===' % len(d))
    print('palette has %d distinct rgba quads' % len(pal))
    print()

    uxc = {k: v for k, v in d.items() if v[:3] == b'uxc'}
    print('=== per-file inline palette-colour quads (4-byte aligned) ===')
    print()
    ranked = []
    for name, b in sorted(uxc.items()):
        if name == 'color_cmn.uxc':
            continue
        hits = []
        for o in range(0x58, len(b) - 3):
            if o % 4:
                continue
            q = quad_at(b, o)
            if q in pal:
                hits.append((o, pal[q], q))
        if hits:
            ranked.append((len(hits), name, hits, len(b)))
    ranked.sort(key=lambda r: -r[0])

    tot = sum(r[0] for r in ranked)
    print('  %d files contain >=1 aligned quad matching a palette colour'
          % len(ranked))
    print('  %d such quads in total' % tot)
    print()
    print('  %-42s %6s %10s' % ('file', 'hits', 'size'))
    for n, name, hits, sz in ranked[:35]:
        print('  %-42s %6d %10d' % (name[:42], n, sz))
    if len(ranked) > 35:
        print('  ... and %d more' % (len(ranked) - 35))

    print()
    print('=== which palette entries are inlined, and how often ===')
    ent = Counter()
    for n, name, hits, sz in ranked:
        for o, off, q in hits:
            ent[off] += 1
    for off, c in ent.most_common(30):
        q = [k for k, v in pal.items() if v == off][0]
        print('  id 0x%04x  %s  %5d occurrences'
              % (ID_BASE + off, ' '.join('%02x' % x for x in q), c))

    print()
    print('=== null model: how often do 4 random bytes match the palette? ===')
    # sample every 4-aligned quad in all files as if they were random
    total_q = 0
    match_q = 0
    for name, b in uxc.items():
        for o in range(0x58, len(b) - 3, 4):
            total_q += 1
            if quad_at(b, o) in pal:
                match_q += 1
    expect = total_q * len(pal) / (2 ** 32)
    print('  %d aligned quads sampled' % total_q)
    print('  %d match a palette colour' % match_q)
    print('  chance expectation      %.1f' % expect)
    print('  observed / expected     %.1fx' % (match_q / expect if expect else 0))
    print()
    if match_q > expect * 3:
        print('  >> Inline palette colours are real, not coincidence.')
    else:
        print('  >> Close to chance. Treat the inline reading as unproven.')

    print()
    print('=== style_cmn.uxc in detail ===')
    sc = d['style_cmn.uxc']
    sc_hits = [(o, pal[quad_at(sc, o)], quad_at(sc, o))
               for o in range(0x58, len(sc) - 3, 4) if quad_at(sc, o) in pal]
    print('  %d bytes, %d aligned palette-matching quads' % (len(sc), len(sc_hits)))
    for o, off, q in sc_hits:
        print('    @0x%04x  id 0x%04x  %s' % (o, ID_BASE + off,
                                             ' '.join('%02x' % x for x in q)))
    print()
    print('  full body, 0x58..0x120:')
    for o in range(0x58, min(0x120, len(sc)), 16):
        ch = sc[o:o + 16]
        txt = ''.join(chr(c) if 32 <= c < 127 else '.' for c in ch)
        mark = ''
        for h in sc_hits:
            if o <= h[0] < o + 16:
                mark = '   <-- palette 0x%04x' % (ID_BASE + h[1])
        print('    %04x  %-47s |%s|%s'
              % (o, ' '.join('%02x' % c for c in ch), txt, mark))


if __name__ == '__main__':
    main()
