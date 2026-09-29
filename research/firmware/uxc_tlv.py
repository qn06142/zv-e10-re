"""Solve the style/view record layout using 0x400c as ground truth.

Two things changed since the last attempt at this, both of which make it
tractable.

1. A correction.  The stride-36 read was closer than the output suggested.  The
   bug was the start offset: records begin at 0x88, not 0x58, and 0x58..0x87 is
   a u16 offset table belonging to this file's header.  Worse, the records do
   not run as one contiguous table -- the marker search found 12 records, then a
   492-byte gap, then 14 more.  The file has sections.  Treating 0x58..EOF as
   one uniform stride is what produced 40 garbage records.

2. A ground truth that removes the guesswork.  The magenta test proved the UI
   resolves colours through palette ids.  So the widget that draws the framing
   guides must name palette entry 0x400c somewhere.  In a view file, whatever
   field holds 0x400c IS the colour reference field -- found by observation, not
   inferred from plausibility.

   This is the key move.  Previous attempts searched for where RGBA *could* sit
   and ranked offsets by density.  That ranks by coincidence.  Instead: find a
   file where we know a specific id is used, and read the field.

Method:
  * locate every marker occurrence by raw search
  * group them into runs where the gap equals the dominant stride; a break
    starts a new section
  * within each section, test candidate strides against the requirement that
    the byte before the marker increases by 1 (the record index)
  * report, per section, the index range and the colours at each candidate
    offset
  * then search view files for 0x400c specifically and report the offsets

The stride test that actually discriminates: if the byte at (marker - 1) counts
up by one across a run of records, that offset is the index field and the
stride is right.  That is a much stronger constraint than "the file length
divides evenly", which is what fooled the last attempt.
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
GROUND_TRUTH = 0x400C          # the id the framing guides resolve through


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


def sections(hits, stride):
    """Split marker hits into runs separated by a gap != stride."""
    out = []
    cur = [hits[0]]
    for a, b in zip(hits, hits[1:]):
        if b - a == stride:
            cur.append(b)
        else:
            out.append(cur)
            cur = [b]
    out.append(cur)
    return out


def index_test(b, run, back):
    """Does the byte `back` positions before each marker count up by one?"""
    vals = [b[h - back] for h in run if h - back >= 0]
    if len(vals) < 4:
        return None, 0
    steps = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
    good = sum(1 for s in steps if s == 1)
    return (good == len(steps)), good / len(steps)


def analyse_style(d):
    print('=' * 76)
    print('style_cmn.uxc: sections, and a real index test')
    print('=' * 76)
    b = d['style_cmn.uxc']
    hits = find_all(b, MARKER)
    print('  %d bytes, %d markers' % (len(b), len(hits)))
    print('  marker offsets: %s' % ' '.join('0x%04x' % h for h in hits))
    gaps = Counter(hits[i + 1] - hits[i] for i in range(len(hits) - 1))
    print('  gaps: %s' % ', '.join('%d x%d' % (k, v) for k, v in gaps.most_common()))
    stride = gaps.most_common(1)[0][0]
    print('  dominant stride %d' % stride)
    print()

    secs = sections(hits, stride)
    print('  %d sections at stride %d:' % (len(secs), stride))
    for i, run in enumerate(secs):
        span = run[-1] + stride - run[0]
        print('    sec %d: %2d recs, 0x%04x..0x%04x (span %d B)'
              % (i, len(run), run[0], run[-1], span))
    print()

    print('  --- index test: which offset before the marker counts up by 1? ---')
    best = None
    for back in range(1, 9):
        oks = []
        for run in secs:
            if len(run) < 4:
                continue
            ok, frac = index_test(b, run, back)
            oks.append((len(run), frac, ok))
        tot = sum(n for n, _f, _o in oks)
        weighted = sum(f * n for n, f, _o in oks) / tot if tot else 0
        allok = all(o for _n, _f, o in oks) if oks else False
        print('    marker-%d : %d usable recs, %.0f%% step-1, all-ok=%s'
              % (back, tot, 100 * weighted, allok))
        if allok and tot >= 8 and (best is None or tot > best[1]):
            best = (back, tot)
    print()
    if best is None:
        print('  no offset counts up cleanly -> the index is not a simple counter,')
        print('  or records are not aligned to the marker as assumed.')
    else:
        back, n = best
        print('  >> index field is at marker-%d (%d recs confirm)' % (back, n))
        for i, run in enumerate(secs):
            if len(run) < 2:
                continue
            idxs = [b[h - back] for h in run]
            print('     sec %d index: %s' % (i, ' '.join('%02x' % v for v in idxs)))
    return stride, back


def rgba_scan(d, stride, back, label):
    print()
    print('--- %s: colour field, by ground truth (0x%04x) ---'
          % (label, GROUND_TRUTH))
    b = d[label]
    hits = find_all(b, MARKER)
    # every offset relative to the marker where 0x400c appears
    at = Counter()
    for h in hits:
        for k in range(-back, stride):
            o = h + k
            if 0 <= o <= len(b) - 2:
                if struct.unpack_from('<H', b, o)[0] == GROUND_TRUTH:
                    at[k] += 1
    for k, n in at.most_common(10):
        print('    marker %+d : %d record(s) hold 0x%04x' % (k, n, GROUND_TRUTH))
    if not at:
        print('    0x%04x does not appear near any marker in this file' % GROUND_TRUTH)


def scan_views(d):
    print()
    print('=' * 76)
    print('which view files reference 0x400c, and where relative to a marker?')
    print('=' * 76)
    rows = []
    for name, b in sorted(d.items()):
        if name.startswith('string_') or name.startswith('image_'):
            continue
        if name in ('color_cmn.uxc', 'style_cmn.uxc'):
            continue
        n = 0
        firsts = []
        s = 0
        while True:
            i = b.find(struct.pack('<H', GROUND_TRUTH), s)
            if i < 0:
                break
            n += 1
            if len(firsts) < 4:
                firsts.append(i)
            s = i + 1
        if n:
            rows.append((n, name, firsts, len(b)))
    rows.sort(reverse=True)
    print('  %d files reference 0x%04x' % (len(rows), GROUND_TRUTH))
    print('  %-42s %5s %10s  first offsets' % ('file', 'hits', 'size'))
    for n, name, firsts, sz in rows[:25]:
        print('  %-42s %5d %10d  %s'
              % (name[:42], n, sz, ' '.join('0x%04x' % f for f in firsts)))
    if len(rows) > 25:
        print('  ... and %d more' % (len(rows) - 25))
    return rows


def main():
    d = load()
    print('=== %d uxc files ===' % len(d))
    stride, back = analyse_style(d)
    rgba_scan(d, stride, back, 'style_cmn.uxc')
    scan_views(d)


if __name__ == '__main__':
    main()
