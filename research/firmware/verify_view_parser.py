"""Independently verify the incoming view parser's central claims.

Three claims worth checking rather than accepting, because two of them correct
work of mine:

C1  The 0x400c trap.  The incoming doc says the apparent 0x400c in
    viewContPbGroup.uxc is inside the section discriminator word 0x7e0c400c,
    not a widget colour reference.  If true, my "one file references 0x400c"
    observation was a false positive -- and my most recent correction, in which
    I claimed 14721 references across the image_* atlases, needs the same
    scrutiny applied to it.

C2  The section descriptor discriminator (high byte 0x7e, then the fixed
    word pattern) actually fires across the corpus, and 60 bytes is right.

C3  The object index table invariant offset[0] == 1 + 2*N holds, and N is
    genuinely a u8.  This is the load-bearing claim: it is what makes object
    boundaries derivable rather than searched for.

C1 is the important one.  It cuts against my last commit, so it gets checked
first and hardest.  Specifically: is the 0c 40 byte pair that I counted 14721
times sitting inside structured words (discriminators, or numeric fields), or is
it a plausible standalone field?

The test that distinguishes: my count was a raw byte-pair search over the whole
file at every offset.  If most hits land inside multi-byte numeric fields whose
value merely happens to contain 0x400c, then my count was measuring nothing
about colour at all.  Checking whether the hit offsets are 4-aligned and what
the enclosing u32 is settles it.

Also re-derives the count the honest way, so the number in the record is
defensible either way.
"""
import struct
import tarfile
from collections import Counter
from pathlib import Path

TGZ = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz')
DESC_WORDS = [(0, 0x7e, 'hi'), (1, 0, '0'), (2, 0, '0'), (3, 2, '2'),
              (4, 0, '0'), (5, 9, '9'), (6, 0, '0'), (7, 0x38, '38')]


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def u16(b, o):
    return struct.unpack_from('<H', b, o)[0]


def load():
    t = tarfile.open(TGZ)
    out = {}
    for m in t.getmembers():
        if m.isfile() and m.name.endswith('.uxc'):
            out[m.name.split('/')[-1]] = t.extractfile(m).read()
    return out


def valid_descriptor(b, o):
    if o < 0 or o + 60 > len(b):
        return False
    w = [u32(b, o + 4 * i) for i in range(15)]
    return (w[0] >> 24 == 0x7e and w[1] == 0 and w[2] == 0 and
            w[3] == 2 and w[4] == 0 and w[5] == 9 and
            w[6] == 0 and w[7] == 0x38 and
            all(x == 0 for x in w[11:15]))


def c1_the_trap(d):
    print('=' * 76)
    print('C1  the 0x400c trap -- is it a colour reference or a byte coincidence?')
    print('=' * 76)
    b = d['viewContPbGroup.uxc']
    print('  viewContPbGroup.uxc %d bytes' % len(b))
    pat = struct.pack('<H', 0x400C)
    hits = [o for o in range(len(b) - 1) if b[o:o + 2] == pat]
    print('  raw byte-pair 0c 40 occurs at %d offset(s): %s'
          % (len(hits), [hex(h) for h in hits]))
    for h in hits:
        w = u32(b, h - 2)
        print('    @0x%04x  enclosing u32 = 0x%08x  (hi byte %02x)'
              % (h, w, w >> 24))
        if w >> 24 == 0x7e:
            print('      ^^ that is a section discriminator (high byte 0x7e).')
            print('      The 0c 40 is the low half of a structural word, NOT a')
            print('      colour id.  The incoming claim is correct.')
    # is it 4-aligned, and does it sit at a field boundary?
    print()
    aligned = sum(1 for h in hits if h % 4 == 0)
    print('  %d of %d hits are 4-byte aligned' % (aligned, len(hits)))
    print()

    # the same test applied to MY claim: 0x400c across the image_* atlases
    print('  --- now the same scrutiny on my own 14721-hit claim ---')
    tot_raw = 0
    tot_in_struct = 0
    per = []
    for name, bb in sorted(d.items()):
        if not name.startswith('image_'):
            continue
        n = 0
        ins = 0
        s = 0
        while True:
            i = bb.find(pat, s)
            if i < 0:
                break
            n += 1
            # does the enclosing u32 look structural?
            if i >= 2:
                w = u32(bb, i - 2)
                if (w >> 24) in (0x7e,) or w == 0 or w == 0xFFFFFFFF:
                    ins += 1
            s = i + 1
        tot_raw += n
        tot_in_struct += ins
        if n:
            per.append((n, ins, name, len(bb)))
    per.sort(reverse=True)
    print('  image_* files: %d raw 0c40 byte-pair hits, %d inside'
          % (tot_raw, tot_in_struct))
    for n, ins, name, sz in per[:8]:
        print('    %-34s %7d raw  %7d structural  %9d B'
              % (name[:34], n, ins, sz))
    print()
    print('  >> My "14721 references" was a raw byte-pair count with no')
    print('     structural validation. In a 27 MB bitmap atlas that number')
    print('     carries no meaning about colour. The count is retracted.')
    return tot_raw


def c2_descriptors(d):
    print()
    print('=' * 76)
    print('C2  does the 0x7e descriptor discriminator fire across the corpus?')
    print('=' * 76)
    views = {k: v for k, v in d.items() if k.startswith('view')}
    files_with = 0
    tot = 0
    counts = []
    for name, b in sorted(views.items()):
        h = [o for o in range(0, len(b) - 59, 4) if valid_descriptor(b, o)]
        if h:
            files_with += 1
        tot += len(h)
        counts.append((len(h), name, len(b)))
    print('  %d view files, %d with >=1 descriptor, %d descriptors total'
          % (len(views), files_with, tot))
    counts.sort()
    print()
    print('  files with ZERO descriptors:')
    zero = [c for c in counts if c[0] == 0]
    for n, name, sz in zero[:20]:
        print('    %-44s %8d B' % (name[:44], sz))
    print('    (%d total)' % len(zero))
    print()
    print('  most sections:')
    for n, name, sz in counts[-6:]:
        print('    %-44s %3d sec  %8d B' % (name[:44], n, sz))
    return tot


def c3_tables(d):
    print()
    print('=' * 76)
    print('C3  the object index table: offset[0] == 1 + 2N, N is a u8')
    print('=' * 76)
    views = {k: v for k, v in d.items() if k.startswith('view')}
    ok = 0
    bad = 0
    nobj = 0
    maxn = 0
    samples = []
    for name, b in sorted(views.items()):
        secs = [o for o in range(0, len(b) - 59, 4) if valid_descriptor(b, o)]
        for i, s in enumerate(secs):
            end = secs[i + 1] if i + 1 < len(secs) else len(b)
            t = s + 60
            if t >= end:
                bad += 1
                continue
            n = b[t]
            if t + 1 + 2 * n > end:
                bad += 1
                continue
            if n == 0:
                ok += 1
                continue
            offs = [u16(b, t + 1 + 2 * j) for j in range(n)]
            if offs[0] != 1 + 2 * n:
                bad += 1
                if len(samples) < 6:
                    samples.append((name, hex(s), n, offs[:6]))
                continue
            if any(offs[j] >= offs[j + 1] for j in range(n - 1)):
                bad += 1
                continue
            ok += 1
            nobj += n
            maxn = max(maxn, n)
    print('  tables valid: %d   invalid: %d' % (ok, bad))
    print('  objects indexed: %d' % nobj)
    print('  largest N: %d  (fits in a u8, max 255)' % maxn)
    if samples:
        print()
        print('  sample invalid tables:')
        for name, s, n, offs in samples:
            print('    %-34s @%s  N=%d  offs=%s' % (name[:34], s, n, offs))
    print()
    if ok > bad * 10:
        print('  >> the invariant holds decisively. This is the load-bearing')
        print('     claim: it makes object boundaries derivable instead of')
        print('     searched for, which is what the marker-gap approach could')
        print('     never do.')
    return ok, bad


def main():
    d = load()
    c1_the_trap(d)
    c2_descriptors(d)
    c3_tables(d)


if __name__ == '__main__':
    main()
