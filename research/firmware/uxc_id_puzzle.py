"""The 0x400c puzzle: the guides follow a palette id, but only one view file
contains it.  Resolve the contradiction from the data we already have.

The observation
---------------
The magenta test proved the live-view framing guides resolve colour through
palette entry 0x400c.  But across all 299 uxc files, 0x400c appears exactly
once: viewContPbGroup.uxc at 0x0e20.  And the guides appear on every screen,
including live view, which has no view file of its own.

Three hypotheses, and they make different predictions:

H1  A widget in a view file names the id.
    Predicts 0x400c appears in the views that draw guides.  One hit in an
    unrelated-looking file argues against it.

H2  The id is compiled into the rendering code as an immediate, and the engine
    indexes the palette with it.  Explains a single occurrence perfectly: the
    views need not mention it at all.
    Not testable offline -- the engine binary is on the card, not in the uxc
    set.  This is the live hypothesis.

H3  The guides inherit a colour from a style, and style_cmn.uxc is the bridge.
    Predicts the guide colour appears in style_cmn.uxc.  We solved that file:
    26 records, RGBA at +12, and the section containing index 0x0b is the one
    with 000000 -- plus a dd dd dd at index 00.

There is a fourth possibility worth taking seriously, and it is the reason this
script exists:

H4  The id is not 0x400c at all.  We changed 0x400c to magenta and the guides
    went magenta, but the guides might resolve 0x400c *indirectly* -- e.g. the
    engine looks up a "guide line colour" style, that style names a palette
    slot, and we happened to hit the slot it uses.  If so, the mapping is
    style -> palette, and the real question is which style.

The way to discriminate: check whether the guide colour's original value, 333333
@ 80% alpha, appears anywhere else.  If the guides resolved through 0x400c
directly, then 0x400c is the guide colour and no other file should need that
exact value.  If it resolves indirectly, some other file should carry a colour
close to it.

Also worth checking, because it is cheap and would be embarrassing to miss:
whether other palette ids are similarly rare.  If EVERY id appears about once
across the view set, the views are not the consumer at all and H2/H4 win by
default.  That is a distribution question, and distributions are answerable
offline.

Method: for each of the 28 palette ids, count occurrences across all view files.
Then classify the ids by frequency.  A uniform "about one hit each" pattern says
the views are incidental.  A skewed pattern says some ids are genuinely used.
"""
import struct
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

CANDIDATES = [
    Path(r'F:\RE_DUMP\TREES\usr_share.tgz'),
    Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz'),
]
STYLE_HIT = 0x400C


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
        if m.isfile() and m.name.endswith('.uxc'):
            out[m.name.split('/')[-1]] = t.extractfile(m).read()
    return out


def palette():
    t = tarfile.open(pick())
    b = t.extractfile('share/app/color_cmn.uxc').read()
    out = {}
    for i in range((len(b) - 0x58) // 8):
        o = 0x58 + i * 8
        cid, const, r, g, bl, a = struct.unpack_from('<HHBBBB', b, o)
        out[cid] = (r, g, bl, a)
    return out


def id_frequency(d, pal):
    print('=' * 76)
    print('how often does each palette id appear across the uxc set?')
    print('=' * 76)
    files = {k: v for k, v in d.items() if k != 'color_cmn.uxc'}
    hits = defaultdict(list)
    for name, b in sorted(files.items()):
        if name.startswith('string_'):
            continue          # ascending u16 offset tables, pure noise
        s = 0
        while True:
            i = b.find(struct.pack('<H', STYLE_HIT if False else 0), s)
            break
        for target in pal:
            pat = struct.pack('<H', target)
            s = 0
            n = 0
            offs = []
            while True:
                i = b.find(pat, s)
                if i < 0:
                    break
                n += 1
                if len(offs) < 3:
                    offs.append(i)
                s = i + 1
            if n:
                hits[target].append((name, n, offs))
    print()
    print('  %-8s %-14s %6s  %s' % ('id', 'rgba', 'hits', 'files'))
    rows = []
    for cid in sorted(pal):
        lst = hits.get(cid, [])
        tot = sum(n for _f, n, _o in lst)
        rows.append((tot, cid, lst))
    for tot, cid, lst in sorted(rows, reverse=True):
        print('  0x%04x  %-14s %6d  %s'
              % (cid, ' '.join('%02x' % x for x in pal[cid]), tot,
                 ', '.join('%s x%d' % (f.split('/')[-1][:28], n) for f, n, _o in lst[:4])))
    return hits


def verdict(hits, pal):
    print()
    print('=' * 76)
    print('reading the distribution')
    print('=' * 76)
    nonzero = [(c, sum(n for _f, n, _o in hits.get(c, [])))
               for c in pal]
    nz = [(c, n) for c, n in nonzero if n]
    zero = [c for c, n in nonzero if not n]
    print('  %d of %d palette ids appear at all in the non-string uxc files'
          % (len(nz), len(pal)))
    print('  %d appear zero times' % len(zero))
    print()
    counts = [n for _c, n in nz]
    if counts:
        print('  hit counts: %s' % ' '.join('%d' % c for c in sorted(counts, reverse=True)))
        print('  max %d, median %d' % (max(counts),
                                       sorted(counts)[len(counts) // 2]))
    print()
    tgt = sum(n for _f, n, _o in hits.get(0x400C, []))
    print('  0x400c (the guide colour): %d hit(s)' % tgt)
    if tgt <= 1 and zero:
        print()
        print('  >> Most palette ids appear zero or one time, and 0x400c is among')
        print('     the rarest. The view files are therefore NOT the consumer of')
        print('     the palette. H1 is out.')
        print()
        print('  >> That leaves the compiled-in-immediate explanation (H2) or an')
        print('     indirect style lookup (H4). Both point away from the uxc set')
        print('     and toward the engine binary, which is on the card and not in')
        print('     this archive.')
        print()
        print('  >> Practical consequence: editing view files for colour is')
        print('     probably wasted effort. colour_cmn.uxc remains the one')
        print('     confirmed lever, and style_cmn.uxc is the next best candidate')
        print('     because it is small, solved, and the only other file with a')
        print('     dense population of palette-matching quads.')


def guide_value_elsewhere(d, pal):
    print()
    print('=' * 76)
    print('does 333333 @ 80%% alpha appear anywhere else? (H4 check)')
    print('=' * 76)
    target = bytes([0x33, 0x33, 0x33, 0x80])
    hits = []
    for name, b in sorted(d.items()):
        s = 0
        while True:
            i = b.find(target, s)
            if i < 0:
                break
            hits.append((name, i))
            s = i + 1
    print('  %d occurrence(s) of 33 33 33 80' % len(hits))
    for name, i in hits[:20]:
        print('    %-44s @0x%04x' % (name[:44], i))
    if len(hits) == 1 and hits[0][0] == 'color_cmn.uxc':
        print()
        print('  >> unique to the palette. So the guides most likely resolve')
        print('     0x400c directly, and no other file duplicates its value.')
    else:
        print()
        print('  >> the value appears in other files too, which is consistent with')
        print('     an indirect lookup: some style carries the same colour and the')
        print('     guides may be drawn from the style, with the palette change')
        print('     appearing to work because the values coincided.')


def main():
    d = load()
    pal = palette()
    print('palette: %d ids, 0x%04x..0x%04x' % (len(pal), min(pal), max(pal)))
    print('archive: %s' % pick().name)
    print()
    hits = id_frequency(d, pal)
    verdict(hits, pal)
    guide_value_elsewhere(d, pal)


if __name__ == '__main__':
    main()
