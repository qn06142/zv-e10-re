"""style_cmn.uxc record: 36 bytes, index at +0, confirmed. Now find the colour.

uxc_tlv.py settled the layout with a real discriminator rather than a
length-divides-evenly guess: the byte at marker-1 counts up by one across all
22 usable records (100%), while marker-2..marker-8 all score 0%.  So:

    stride 36, index u8 at +0, marker a0 07 26 08 at +1..+4

and the records live in sections (12 recs, gap, 2 recs, gap, 10 recs) starting
at 0x88 -- not one uniform table from 0x58 as the earlier attempt assumed.

Now for the colour field.  The obvious test came back negative: 0x400c does not
appear anywhere in style_cmn.uxc, and across all 299 uxc files it appears in
exactly one (viewContPbGroup.uxc, a single hit at 0x0e20).  So the guide-line
widget does not name palette id 0x400c, and the assumption that it would was
wrong.  The magenta result proved the *engine* resolves through the palette; it
does not follow that every widget spells out the id.

So the colour has to be found from the record structure instead.  The method
that works: for each byte offset within the 36-byte record, look across all
records and find the offset whose values are (a) always in a plausible colour
range, and (b) actually vary.  A field that is always the same colour, or
always zero, is not the colour field -- that was the trap last time, where 40
of 50 records read as the marker being mistaken for a colour.

The strongest additional test: the palette is authoritative, so somewhere in
this record there must be a link to a palette id.  Even if it is not a literal
0x4xxx, an index into the palette would be a small integer.  So also report,
per offset, the distribution of values -- a field taking values 0..27 across
records is a palette index, and that would be the real handle.

If a palette index exists, then style_cmn.uxc is not inlining colours at all --
it is indexing them, and the earlier "9212x chance" result would need
reinterpreting: the inline quads would then be defaults, not the live path.
"""
import struct
import tarfile
from collections import Counter
from pathlib import Path

CANDIDATES = [
    Path(r'F:\RE_DUMP\TREES\usr_share.tgz'),
    Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz'),
]
MARKER = bytes([0xa0, 0x07, 0x26, 0x08])
STRIDE = 36
NREC = 26


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


def find_all(buf, pat):
    out, s = [], 0
    while True:
        i = buf.find(pat, s)
        if i < 0:
            return out
        out.append(i)
        s = i + 1


def main():
    d = load()
    b = d['style_cmn.uxc']
    hits = find_all(b, MARKER)
    # record start = marker - 1
    starts = [h - 1 for h in hits]
    print('=== style_cmn.uxc: %d records, stride %d, start at marker-1 ==='
          % (len(starts), STRIDE))
    print('  record starts: %s' % ' '.join('0x%04x' % s for s in starts))
    print()

    # sanity: index field must be the rising counter
    idx = [b[s] for s in starts]
    print('  index at +0: %s' % ' '.join('%02x' % v for v in idx))
    print()

    print('=== per-offset field analysis across all %d records ===' % len(starts))
    print()
    print('  %-4s %-22s %-7s %-7s %s' % ('off', 'distinct', 'varies', 'range', 'verdict'))
    verdicts = {}
    for k in range(STRIDE):
        vals = []
        for s in starts:
            o = s + k
            vals.append(b[o] if o < len(b) else None)
        real = [v for v in vals if v is not None]
        dis = len(set(real))
        mn, mx = (min(real), max(real)) if real else (0, 0)
        varies = dis > 1
        # a palette index would take small values 0..0x22
        pal_idx = varies and mx <= 0x22 and mn >= 0
        # a colour field: 4 consecutive bytes all plausible, varying
        verdict = ''
        if k + 3 < STRIDE:
            q = [tuple(b[s + k + j] for j in range(4)) for s in starts
                 if s + k + 3 < len(b)]
            alldiff = len(set(q))
            # alpha is almost always 0xff or 0x80 for a UI colour
            alphas = Counter(x[3] for x in q)
            if alldiff > 1 and alphas.most_common(1)[0][0] in (0xff, 0x80, 0x99, 0xcc):
                verdict = 'COLOUR? %d distinct quads, alpha=%s' % (
                    alldiff, dict(alphas.most_common(3)))
        if pal_idx and not verdict:
            verdict = 'PALETTE INDEX? all values 0..0x%02x' % mx
        print('  %-4d %-22d %-7s %-7s %s'
              % (k, dis, 'yes' if varies else 'NO', '0x%02x-0x%02x' % (mn, mx), verdict))
        verdicts[k] = verdict

    print()
    print('=== candidate colour quads, dumped ===')
    for k in range(STRIDE - 3):
        q = [tuple(b[s + k + j] for j in range(4)) for s in starts
             if s + k + 3 < len(b)]
        if len(set(q)) < 2:
            continue
        alphas = Counter(x[3] for x in q)
        if alphas.most_common(1)[0][0] not in (0xff, 0x80, 0x99, 0xcc, 0x4c, 0x44, 0x88):
            continue
        print()
        print('  offset +%d:' % k)
        for s in starts:
            o = s + k
            v = tuple(b[o:o + 4])
            print('    @0x%04x  %s   index %02x'
                  % (s, ' '.join('%02x' % x for x in v), b[s]))


if __name__ == '__main__':
    main()
