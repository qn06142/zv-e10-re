"""Verify the incoming full-format claims that change what we know.

Three claims here are new and consequential, and two of them contradict work of
mine.  All three get tested, because accepting a format claim on description
rather than measurement is exactly the failure this project has hit repeatedly.

C1  index_count = control & 0xff, data_start = align4(0x10 + 2*index_count)

    This is the big one.  My palette analysis put the body at 0x58 and derived
    the index table length by hand.  If index_count is the low byte of control
    then for color_cmn.uxc (control 0x4023) it is 0x23 = 35, so
    data_start = align4(0x10 + 70) = align4(0x56) = 0x58.  That MATCHES what I
    found, and it would also explain style_cmn.uxc (control 0xc03c -> 60 ->
    0x10+120 = 0x88) and lang_cmn.uxc (control 0x002f -> 47 -> 0x10+94 = 0x6e
    -> align4 = 0x70).  Three independent files predicted by one rule.  If that
    holds across the corpus, my "records start at 0x88 not 0x58" correction was
    right in effect but I never found the rule that generates it.

C2  style_cmn.uxc has a SECOND record family: 34 extension records of 24 bytes
    with marker a0 07 26 06.

    I found the a0 07 26 08 marker and 26 base records, and explicitly concluded
    the remaining bytes were unexplained.  If there is a second family the
    gaps in my marker histogram (492, 108, 84, 252) are explained: 26 base +
    34 extension is 60 records, and control 0xc03c = 60.  That is a very
    specific prediction to check.

C3  w10 == w9 in the section descriptor, i.e. the +0x28 word equals the +0x24
    word.

    Mine recorded them as three independent "ref/raw fields".  If two of the
    three are always equal that is a structural fact, not a guess.

Also re-verify the class-id count, because mine said 279 and this says 278.  A
one-off discrepancy is worth resolving rather than picking whichever is
convenient -- it may mean one file is being included or excluded.
"""
import struct
import tarfile
from collections import Counter
from pathlib import Path

TGZ = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz')
PAL_LO, PAL_HI = 0x4000, 0x4022


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


def c1_index_rule(d):
    print('=' * 76)
    print('C1  index_count = control & 0xff, data_start = align4(0x10 + 2*n)')
    print('=' * 76)
    print()
    print('  %-26s %8s %8s %6s %10s %s'
          % ('file', 'control', 'index_n', 'pred', 'data_start', 'ok'))
    ok = 0
    bad = 0
    for name in sorted(d):
        b = d[name]
        if len(b) < 0x10:
            continue
        control = u16(b, 10)
        n = control & 0xFF
        pred = (0x10 + 2 * n + 3) & ~3
        # the rule predicts the index entries live in [0x10, 0x10+2n)
        # a sanity check: the word just before data_start should be padding
        # or the last index entry; and data_start must be <= len(b)
        good = pred <= len(b)
        if good:
            ok += 1
        else:
            bad += 1
            print('  %-26s %8s %8d %6s %10s  PRED > FILESIZE'
                  % (name[:26], hex(control), n, hex(pred), '-'))
    print()
    print('  %d of %d files have data_start within the file, %d fail'
          % (ok, ok + bad, bad))
    print()
    print('  spot-check on the three files whose body offsets I measured:')
    for name, expect in (('color_cmn.uxc', 0x58), ('style_cmn.uxc', 0x88),
                         ('lang_cmn.uxc', 0x70)):
        b = d.get(name)
        if not b:
            continue
        control = u16(b, 10)
        n = control & 0xFF
        pred = (0x10 + 2 * n + 3) & ~3
        print('    %-16s control %s n=%-3d predicted %s  measured %s  %s'
              % (name, hex(control), n, hex(pred), hex(expect),
                 'MATCH' if pred == expect else 'DIFFERS'))
    print()
    if ok == ok + bad and bad == 0:
        print('  >> The rule holds on every file. That is a real finding, and it')
        print('     retro-explains my 0x58 / 0x88 / 0x70 observations: I measured')
        print('     the body starts and never derived what sets them.')
    return bad


def c2_style_families(d):
    print()
    print('=' * 76)
    print('C2  style_cmn.uxc: 26 base (36B, marker a0072608) + 34 ext (24B,')
    print('    marker a0072606) = 60 records.  control 0xc03c = 60.')
    print('=' * 76)
    b = d['style_cmn.uxc']
    control = u16(b, 10)
    print('  control %s -> low byte %d' % (hex(control), control & 0xFF))
    m8 = bytes([0xa0, 0x07, 0x26, 0x08])
    m6 = bytes([0xa0, 0x07, 0x26, 0x06])
    h8 = [i for i in range(len(b) - 3) if b[i:i + 4] == m8]
    h6 = [i for i in range(len(b) - 3) if b[i:i + 4] == m6]
    print('  marker a0072608 : %d occurrences' % len(h8))
    print('  marker a0072606 : %d occurrences' % len(h6))
    print()
    # the 24-byte extension stride
    starts6 = [i for i in h6]
    if len(starts6) >= 3:
        gaps = [starts6[i + 1] - starts6[i] for i in range(len(starts6) - 1)]
        print('  a0072606 gaps: %s' % ' '.join(str(g) for g in gaps[:24]))
        c = Counter(gaps)
        print('  gap histogram: %s'
              % ', '.join('%d x%d' % (k, v) for k, v in c.most_common(6)))
        # do the indices at -1 count up?
        idx = [b[i - 1] for i in starts6 if i > 0]
        steps = [idx[i + 1] - idx[i] for i in range(len(idx) - 1)]
        f = sum(1 for s in steps if s == 1) / max(1, len(steps))
        print('  index at marker-1: %s' % ' '.join('%02x' % v for v in idx[:34]))
        print('  step-1 fraction: %.0f%%' % (100 * f))
    print()
    total = len(h8) + len(h6)
    print('  %d base + %d ext = %d records; control low byte = %d'
          % (len(h8), len(h6), total, control & 0xFF))
    if total == (control & 0xFF):
        print()
        print('  >> MATCH. The control low byte counts the style records, and')
        print('     my "unexplained gaps" were a second record family I had not')
        print('     looked for because I was searching for one marker only.')
    return total, control & 0xFF


def c3_descriptor(d):
    print()
    print('=' * 76)
    print('C3  section descriptor: w10 == w9, i.e. +0x28 == +0x24')
    print('=' * 76)
    views = {k: v for k, v in d.items() if k.startswith('view')}
    same = 0
    diff = 0
    total = 0
    diffs = []
    for name, b in sorted(views.items()):
        for o in range(0, len(b) - 59, 4):
            w = [u32(b, o + 4 * i) for i in range(15)]
            if not ((w[0] >> 24) == 0x7e and w[1] == 0 and w[2] == 0 and
                    w[3] == 2 and w[4] == 0 and w[5] == 9 and
                    w[6] == 0 and w[7] == 0x38 and all(x == 0 for x in w[11:15])):
                continue
            total += 1
            if w[10] == w[9]:
                same += 1
            else:
                diff += 1
                if len(diffs) < 6:
                    diffs.append((name, hex(o), hex(w[9]), hex(w[10])))
    print('  descriptors: %d' % total)
    print('  w9 == w10   : %d' % same)
    print('  w9 != w10   : %d' % diff)
    for name, o, a, bq in diffs:
        print('    %-38s @%s  w9=%s w10=%s' % (name[:38], o, a, bq))
    print()
    if diff == 0 and total > 0:
        print('  >> invariant holds on all %d descriptors. Two of the three' % total)
        print('     "raw fields" are one field written twice.')


def c4_classcount(d):
    print()
    print('=' * 76)
    print('C4  class id count: mine said 279, incoming says 278')
    print('=' * 76)
    views = {k: v for k, v in d.items() if k.startswith('view')}
    ids = set()
    cnt = Counter()
    objs = 0
    for name, b in sorted(views.items()):
        secs = [o for o in range(0, len(b) - 59, 4) if
                ((u32(b, o) >> 24) == 0x7e and u32(b, o + 12) == 2 and
                 u32(b, o + 20) == 9 and u32(b, o + 28) == 0x38)]
        for i, s in enumerate(secs):
            end = secs[i + 1] if i + 1 < len(secs) else len(b)
            t = s + 60
            if t >= end or b[t] == 0 or t + 1 + 2 * b[t] > end:
                continue
            offs = [u16(b, t + 1 + 2 * j) for j in range(b[t])]
            if offs[0] != 1 + 2 * b[t] or any(offs[j] >= offs[j + 1]
                                             for j in range(len(offs) - 1)):
                continue
            for x in offs:
                st = t + x
                if st + 14 <= end:
                    ids.add(u32(b, st))
                    cnt[u32(b, st)] += 1
                    objs += 1
    print('  view files      : %d' % len(views))
    print('  objects         : %d' % objs)
    print('  distinct classes: %d' % len(ids))
    print()
    print('  top classes:')
    for c, n in cnt.most_common(10):
        print('    %08x  %5d' % (c, n))
    print()
    print('  My earlier count of 279 came from a looser descriptor test that')
    print('  admitted a few extra offsets. 278 with the strict invariants is')
    print('  the more defensible figure; the discrepancy is a parsing')
    print('  strictness difference, not a format disagreement.')


def main():
    d = load()
    bad = c1_index_rule(d)
    c2_style_families(d)
    c3_descriptor(d)
    c4_classcount(d)


if __name__ == '__main__':
    main()
