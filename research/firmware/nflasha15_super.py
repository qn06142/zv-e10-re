"""Confirm nflasha15 is the ext root holding /usr/share/app, and read its superblock.

flash_fs_probe.py found a filesystem magic at offset 0x438 in nflasha15 and
nflasha7.  0x438 is the canonical ext superblock location (superblock starts at
byte 1024; the magic 0xEF53 lives 0x38 bytes in), so that is a real superblock
and not a compressed-data coincidence.  nflasha15 is 300 MB and contains 251
uxc container signatures plus 2 literal color_cmn.uxc strings.

This script proves it properly, and answers the last question that gates the
palette plan: is the root filesystem mounted read-only?

That comes out of the superblock's s_feature_compat / s_feature_incompat /
s_feature_ro_compat feature flags, plus the journal.  Specifically:

  EXT4_FEATURE_COMPAT_RO_COMPAT   (0x0008)  metadata_csum seed
  EXT4_FEATURE_INCOMPAT_RO_COMPAT (0x0001)  the filesystem is mounted ro

If RO_COMPAT is clear, the fs is writable in principle.  Whether the kernel
mounted it ro is a mount-time decision we still confirm live, but a writable
partition is necessary, and this is the necessary condition.

Also read the block group descriptor to get the block size, so the geometry is
understood, and locate the /usr/share/app directory entries by searching for
the color_cmn.uxc literal in context -- an ext directory entry gives us the
inode, and from there the real file layout.
"""
import struct
from pathlib import Path

IMG = Path(r'F:\RE_DUMP\nflasha15.img')
SB_OFF = 1024
MAGIC = 0xEF53


def main():
    with IMG.open('rb') as f:
        f.seek(SB_OFF)
        sb = f.read(1024)

    (s_inodes_count, s_blocks_count_lo, s_r_blocks_count_lo, s_free_blocks_count_lo,
     s_free_inodes_count, s_first_data_block, s_log_block_size,
     s_log_cluster_size, s_blocks_per_group, s_clusters_per_group,
     s_inodes_per_group) = struct.unpack_from('<11I', sb, 0)

    (magic,) = struct.unpack_from('<H', sb, 0x38)
    (state,) = struct.unpack_from('<H', sb, 0x3A)
    (s_inode_size,) = struct.unpack_from('<H', sb, 0x58)
    (s_feature_compat,) = struct.unpack_from('<I', sb, 0x5C)
    (s_feature_incompat,) = struct.unpack_from('<I', sb, 0x60)
    (s_feature_ro_compat,) = struct.unpack_from('<I', sb, 0x64)
    (s_uuid,) = struct.unpack_from('<16s', sb, 0x68)
    (s_volume_name,) = struct.unpack_from('<16s', sb, 0x78)

    block = 1024 << s_log_block_size

    print('=== %s ===' % IMG.name)
    print('  superblock magic 0x%04x  %s' % (magic, 'OK' if magic == MAGIC else 'BAD'))
    print('  state 0x%04x  %s' % (state, {1: 'clean', 2: 'errors'}.get(state, '?')))
    print('  volume name %r' % s_volume_name.rstrip(b'\x00'))
    print('  uuid %s' % s_uuid.hex())
    print()
    print('  block size          %d bytes' % block)
    print('  inodes              %d' % s_inodes_count)
    print('  blocks              %d  (%.1f MB)' % (s_blocks_count_lo, s_blocks_count_lo * block / 1048576))
    print('  free blocks         %d' % s_free_blocks_count_lo)
    print('  free inodes         %d' % s_free_inodes_count)
    print('  first data block    %d' % s_first_data_block)
    print('  blocks per group    %d' % s_blocks_per_group)
    print('  inodes per group    %d' % s_inodes_per_group)
    print('  inode size          %d' % s_inode_size)
    print()
    print('  feature_compat      0x%08x' % s_feature_compat)
    print('  feature_incompat    0x%08x' % s_feature_incompat)
    print('  feature_ro_compat  0x%08x' % s_feature_ro_compat)
    print()
    print('  EXT4_FEATURE_INCOMPAT_RO_COMPAT (0x1)   %s  <- fs is read-only'
          % ('SET' if s_feature_incompat & 0x1 else 'clear'))
    print('  EXT3_FEATURE_RO_COMPAT (0x40)           %s'
          % ('SET' if s_feature_ro_compat & 0x40 else 'clear'))
    print()
    known = []
    for bit, name in ((0x1, 'FILETYPE'), (0x2, 'RECOVER'), (0x4, 'JOURNAL_DEV'),
                      (0x8, 'META_BG'), (0x10, 'EXTENTS'), (0x40, '64BIT'),
                      (0x100, 'FLEX_BG'), (0x200, 'HAS_JOURNAL'),
                      (0x400, 'META_CSUM'), (0x800, 'Csum_seed'),
                      (0x1000, 'LARGEDIR'), (0x2000, 'INLINE_DATA'),
                      (0x4000, 'ENCRYPT'), (0x8000, 'CASEFOLD'),
                      (0x10000, 'INCOMPAT_CSUM')):
        if s_feature_incompat & bit:
            known.append('incompat:' + name)
    for bit, name in ((0x1, 'DIRTY'), (0x2, 'COMPAT_HAS_JOURNAL'),
                      (0x4, 'EXT_ATTR'), (0x8, 'RESIZE_INODE'),
                      (0x10, 'DIR_INDEX'), (0x20, 'LAZY_BG'),
                      (0x40, 'MINOR_META_BG'), (0x100, 'EXCLUDE_INODE'),
                      (0x200, 'EXCLUDE_BITMAP'), (0x400, 'SGROUP_RO_COMPAT'),
                      (0x800, 'Csum_SEED'), (0x1000, 'LQUOTA'),
                      (0x2000, 'META_BG'), (0x4000, 'REPLICA')):
        if s_feature_ro_compat & bit:
            known.append('ro_compat:' + name)
    print('  decoded features: %s' % (', '.join(known) or '(none)'))
    print()
    if s_feature_incompat & 0x1:
        print('  VERDICT: this filesystem was created read-only. Not writable.')
    else:
        print('  VERDICT: filesystem supports write. Whether the kernel mounted')
        print('          it ro is a mount-time choice, still to confirm live,')
        print('          but the necessary condition is met.')

    # locate the color_cmn.uxc directory entries and decode them
    print()
    print('=== locating color_cmn.uxc in the ext directory ===')
    data = IMG.read_bytes()
    lit = b'color_cmn.uxc'
    s = 0
    while True:
        i = data.find(lit, s)
        if i < 0:
            break
        # an ext4 dir entry: inode(u32) rec_len(u16) name_len(u8) file_type(u8) name[]
        # name is preceded by 12 bytes of header, and the name starts at
        # entry_start+8, so the entry starts 8 bytes before the name
        estart = i - 8
        ino, rec_len, nlen, ftype = struct.unpack_from('<I H B B', data, estart)
        print('  @0x%08x  inode %-8d rec_len %-4d name_len %-3d type %d  %r'
              % (estart, ino, rec_len, nlen, ftype,
                 data[estart + 8:estart + 8 + nlen].decode('latin1', 'replace')))
        # show neighbouring entries
        lo = estart
        for k in range(-3, 4):
            o = estart + k * 32
            if o < 0 or o + 8 > len(data):
                continue
            try:
                ii, rl, nl, ft = struct.unpack_from('<I H B B', data, o)
            except Exception:
                continue
            if not (0 < rl <= 4096) or nl == 0 or nl > 255:
                continue
            nm = data[o + 8:o + 8 + nl]
            if all(32 <= c < 127 for c in nm):
                print('      %s@0x%08x inode %-8d len %-3d type %d %r'
                      % ('>' if k == 0 else ' ', o, ii, rl, ft,
                         nm.decode('latin1')))
        s = i + 1


if __name__ == '__main__':
    main()
