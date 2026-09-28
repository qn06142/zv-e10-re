"""The index_count rule: which header word is the count, and where does it fail.

UXC_FORMAT_FULL.md claims index_count = control & 0xff, data_start =
align4(0x10 + 2*index_count).  My check rejected it -- but my check was
partly wrong, and separating the two matters.

My test read `control` from offset 0x0a.  For color_cmn.uxc that gave 0x4a, and
0x4a & 0xff = 74, predicting data_start 0xa4 against a measured 0x58.  So on the
palette file the rule as I read it is wrong.

But the incoming document's own worked examples say something different, and
re-reading them shows my reader is off by one field.  The document's header is:

    0x08 u16 stream_version    0x0a u16 resource_id
    0x0c u16 control           0x0e u16 aux

and it gives color_cmn.uxc as control 0x4023 with index_count 35.  My file
layout has 0x0a = 0x4a and 0x0c = 0x4023.  So `control` is at 0x0c, not 0x0a,
and resource_id is at 0x0a.  With control read correctly:

    color_cmn.uxc   control 0x4023  n=35   data_start = align4(0x10+70) = 0x58   measured 0x58  MATCH
    style_cmn.uxc   control 0xc03c  n=60   data_start = align4(0x10+120) = 0x88  measured 0x88  MATCH
    lang_cmn.uxc    control 0x002f  n=47   data_start = align4(0x10+94) = 0x70   measured 0x70  MATCH
    viewBaseMenu    control 0x2001  n=1    data_start = align4(0x10+2)  = 0x14

That is the rule holding on three files I had independently measured, plus the
document's own fourth example.  The earlier "12 of 302 fail" was my 0x0a
misread producing nonsense counts, not a defect in the rule.

So the claim survives, and it explains something I never understood: I had
observed body starts at 0x58, 0x88 and 0x70, worked out by hand for each file,
and never noticed a single rule generated all three.  The rule is one line.

The real test now, and the one that can still falsify it: does index_count also
predict the *contents* of the table?  Specifically, the document says entries
are relative offsets from data_start with 0xffff meaning absent.  That is
checkable -- every non-0xffff entry should point inside the file.  If the rule
were wrong about the base, most entries would point nowhere.
"""
import struct
import tarfile
from collections import Counter
from pathlib import Path

TGZ = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz')


def u16(b, o):
    return struct.unpack_from('<H', b, o)[0]


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def load():
    t = tarfile.open(TGZ)
    out = {}
    for m in t.getmembers():
        if m.isfile() and m.name.endswith(('.uxc', '.uxb', '.xdb')):
            out[m.name.split('/')[-1]] = t.extractfile(m).read()
    return out


def main():
    d = load()
    print('=' * 76)
    print('the rule, with control read at 0x0c (not 0x0a)')
    print('  index_count = control & 0xff')
    print('  data_start  = align4(0x10 + 2 * index_count)')
    print('=' * 76)
    print()
    ok = bad = 0
    fails = []
    for name in sorted(d):
        b = d[name]
        if len(b) < 0x10:
            continue
        control = u16(b, 0x0C)
        n = control & 0xFF
        pred = (0x10 + 2 * n + 3) & ~3
        if pred <= len(b):
            ok += 1
        else:
            bad += 1
            fails.append((name, control, n, pred, len(b)))
    print('  %d of %d files: predicted data_start is inside the file' % (ok, ok + bad))
    print()
    for name, c, n, p, sz in fails:
        print('    %-34s control %s n=%-3d pred %s  size %d'
              % (name[:34], hex(c), n, hex(p), sz))
    print()
    print('  spot-checks against offsets measured earlier in this project:')
    for name, expect in (('color_cmn.uxc', 0x58), ('style_cmn.uxc', 0x88),
                         ('lang_cmn.uxc', 0x70), ('viewBaseMenu.uxc', 0x14)):
        b = d.get(name)
        if not b:
            continue
        c = u16(b, 0x0C)
        n = c & 0xFF
        pred = (0x10 + 2 * n + 3) & ~3
        print('    %-18s control %s n=%-3d predicted %s  expected %s  %s'
              % (name, hex(c), n, hex(pred), hex(expect),
                 'MATCH' if pred == expect else 'DIFFERS'))
    print()

    # the content test: do the index entries point inside the file?
    print('=' * 76)
    print('the falsifiable part: are the index entries offsets from data_start?')
    print('=' * 76)
    tot = inrange = absent = 0
    per = []
    for name in sorted(d):
        b = d[name]
        if len(b) < 0x10:
            continue
        c = u16(b, 0x0C)
        n = c & 0xFF
        ds = (0x10 + 2 * n + 3) & ~3
        if ds > len(b):
            continue
        good = 0
        seen = 0
        for i in range(n):
            v = u16(b, 0x10 + 2 * i)
            if v == 0xFFFF:
                absent += 1
                continue
            seen += 1
            tot += 1
            if ds + v < len(b):
                good += 1
                inrange += 1
        if seen:
            per.append((good / seen, name, seen, good, n))
    print('  non-absent index entries: %d' % tot)
    print('  absent (0xffff)          : %d' % absent)
    print('  land inside the file     : %d  (%.1f%%)' % (inrange, 100.0 * inrange / tot))
    print()
    per.sort()
    print('  worst 12 files:')
    for frac, name, seen, good, n in per[:12]:
        print('    %-40s %5d/%-5d = %5.1f%%' % (name[:40], good, seen, 100 * frac))
    print()
    best = [p for p in per if p[0] > 0.95]
    print('  files where >95%% of entries land in range: %d of %d' % (len(best), len(per)))
    print()
    if inrange == tot:
        print('  >> every non-absent entry is a valid offset from data_start.')
        print('     The rule is confirmed on content, not just on arithmetic.')
    elif inrange > 0.9 * tot:
        print('  >> overwhelmingly confirmed; the residue is worth a look but')
        print('     the base is right.')
    else:
        print('  >> NOT confirmed. The base or the semantics are wrong.')


if __name__ == '__main__':
    main()
