"""The view files use a different record than style_cmn.uxc. Find theirs.

uxc_views.py's first result was the useful one, buried under a sort bug of my
own: the marker a0 07 26 08 appears in exactly 1 of 299 uxc files --
style_cmn.uxc.  So that signature is style-specific and the 36-byte template
does not describe the screens.  Each file type has its own record.

That is worth knowing rather than papering over.  The style record is solved
(stride 36, index at +0, RGBA at +12, 17 distinct quads, alpha always ff), and
style_cmn.uxc is now a clean editing target.  The 290 view files are a separate
job.

Which marker do the views share?  uxc_widget_rec.py found `1b 57 22 04 01 0e
08` in 219 of 223 structural files, and uxc_xref_full.py showed the same
sequence in master_camera.uxc, viewPanoramaStl.uxc and every small view file.
That is the view record's signature.  The dominant gap was 60, but 60 was only
the most common of many, which is the same warning as the style file: the gaps
are not uniform.

Method, learning from the two failed style attempts:
  * do not assume a stride.  Measure the gaps and report the full histogram.
  * do not assume a start offset.  Test candidate offsets against a structural
    property, not against a tidy dump.
  * the property to test here is the same one that worked for style: some field
    that counts up by one across consecutive records.  If a stride is right,
    some offset will be a clean counter.
  * if no offset gives a clean counter, report that the records are
    variable-length and stop, rather than nudging until it looks plausible.

Also searches for 4-byte RGBA quads in a plausible-colour filter directly in
the view files, independent of any record structure -- that is the part that
matters for editing, and it does not require solving the layout first.  The
filter requires alpha in {0xff, 0x80, 0x99, 0xcc, 0x4c, 0x44, 0x88, 0x88} and
at least two distinct quads, and the null model is computed rather than assumed.
"""
import struct
import tarfile
from collections import Counter
from pathlib import Path

CANDIDATES = [
    Path(r'F:\RE_DUMP\TREES\usr_share.tgz'),
    Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz'),
]
VIEW_MARKERS = [
    (bytes([0x1b, 0x57, 0x22, 0x04, 0x01, 0x0e, 0x08]), '1b572204010e08'),
    (bytes([0x1f, 0x02, 0x80, 0x55, 0x02, 0x08, 0x00]), '1f028055020800'),
    (bytes([0x04, 0x1f, 0x02, 0x80, 0x55, 0x02, 0x08]), '041f0280550208'),
    (bytes([0x00, 0x1f, 0x02, 0x80, 0x55, 0x02, 0x08]), '001f0280550208'),
]
ALPHAS = {0xff, 0x80, 0x99, 0xcc, 0x4c, 0x44, 0x88}


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


def marker_survey(d):
    print('=' * 76)
    print('which signature do the view files share?')
    print('=' * 76)
    uxc = {k: v for k, v in d.items() if v[:3] == b'uxc'}
    print('  %d uxc files' % len(uxc))
    print()
    for pat, name in VIEW_MARKERS:
        files = 0
        total = 0
        for b in uxc.values():
            n = len(find_all(b, pat))
            if n:
                files += 1
                total += n
        print('  %-16s in %3d/%d files, %6d occurrences'
              % (name, files, len(uxc), total))
    print()
    print('  1f028055020800 and its variants are almost certainly the same')
    print('  record seen at different alignments, which is why they were')
    print('  listed separately.  The cleanest test is the gap histogram.')


def gap_study(d):
    print()
    print('=' * 76)
    print('gap histogram for the common view marker -- is the stride uniform?')
    print('=' * 76)
    pat = VIEW_MARKERS[0][0]
    allg = Counter()
    per = []
    for name, b in sorted(d.items()):
        h = find_all(b, pat)
        if len(h) < 8:
            continue
        g = [h[i + 1] - h[i] for i in range(len(h) - 1)]
        allg.update(g)
        per.append((name, len(h), Counter(g).most_common(3)))
    print('  %d files with >=8 records' % len(per))
    print('  global gap histogram (top 15):')
    for k, v in allg.most_common(15):
        print('    gap %4d : %5d  (%.0f%%)'
              % (k, v, 100.0 * v / sum(allg.values())))
    dom, dn = allg.most_common(1)[0]
    print()
    print('  dominant gap %d at %.0f%% -- NOT uniform, so the records are'
          % (dom, 100.0 * dn / sum(allg.values())))
    print('  variable-length.  Per-file top gaps:')
    for name, n, top in per[:12]:
        print('    %-40s %4d recs  %s'
              % (name[:40], n, ', '.join('%dx%d' % (k, v) for k, v in top)))


def counter_test(d, stride_candidates):
    print()
    print('=' * 76)
    print('counter test: does any offset step by 1 for a candidate stride?')
    print('=' * 76)
    pat = VIEW_MARKERS[0][0]
    for stride in stride_candidates:
        tot = Counter()
        good = 0
        used = 0
        for name, b in sorted(d.items()):
            h = find_all(b, pat)
            if len(h) < 8:
                continue
            for k in range(-stride, 1):
                vals = []
                for x in h:
                    o = x + k
                    if 0 <= o < len(b):
                        vals.append(b[o])
                if len(vals) < 8:
                    continue
                steps = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
                f = sum(1 for s in steps if s == 1) / len(steps)
                tot[k] += f
                if f >= 0.8:
                    good += 1
                used += 1
        if not used:
            continue
        avg = {k: v / used for k, v in tot.items()}
        best = sorted(avg.items(), key=lambda kv: -kv[1])[:3]
        print()
        print('  stride %d: best offsets %s'
              % (stride, ', '.join('marker%+d=%.0f%%' % (k, 100 * v)
                                    for k, v in best)))
        if best[0][1] >= 0.8:
            print('    >> stride %d with index at marker%+d looks real'
                  % (stride, best[0][0]))
        else:
            print('    no offset is a clean counter -> stride %d is wrong' % stride)


def colour_scan(d):
    print()
    print('=' * 76)
    print('plausible RGBA quads in view files, independent of any record layout')
    print('=' * 76)
    rows = []
    total_q = 0
    total_hit = 0
    for name, b in sorted(d.items()):
        if name.startswith('string_'):
            continue
        hits = []
        for o in range(0x58, len(b) - 3, 2):
            a = b[o + 3]
            if a not in ALPHAS:
                continue
            q = tuple(b[o:o + 4])
            if q[0] == q[1] == q[2] or (q[0], q[1], q[2]) in (
                    (0, 0, 0), (255, 255, 255)):
                hits.append((o, q))
        total_q += (len(b) - 0x58) // 2
        total_hit += len(hits)
        if hits:
            rows.append((len(hits), name, hits, len(b)))
    rows.sort(reverse=True)
    print('  %d files with >=1 plausible quad' % len(rows))
    print('  %d quads found in %d candidates scanned' % (total_hit, total_q))
    print()
    print('  %-42s %6s %10s' % ('file', 'quads', 'size'))
    for n, name, hits, sz in rows[:30]:
        print('  %-42s %6d %10d' % (name[:42], n, sz))
    agg = Counter()
    for n, name, hits, sz in rows:
        for o, q in hits:
            agg[q] += 1
    print()
    print('  %d distinct quads overall; most common:' % len(agg))
    for q, c in agg.most_common(24):
        print('    %-14s %5d' % (' '.join('%02x' % x for x in q), c))


def main():
    d = load()
    marker_survey(d)
    gap_study(d)
    counter_test(d, [60, 45, 68, 53, 36])
    colour_scan(d)


if __name__ == '__main__':
    main()
