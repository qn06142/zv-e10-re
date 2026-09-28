"""Can we write /usr/share/app/color_cmn.uxc?  Answered from the live mount table.

The ext superblock said nflasha15 permits writes (RO_COMPAT clear).  The mount
table says otherwise, and the mount table wins:

    /dev/nflasha15 /usr ext2 ro,relatime,errors=continue 0 0
    /dev/nflasha7  /    ext2 ro,relatime,errors=continue 0 0

Note "ext2", not ext4 -- the kernel mounts this without a journal, which is the
old-style ext2 that gets mounted read-only.  The superblock feature flags
describe what the filesystem can do; the mount option describes what the kernel
did.  Only the second one decides whether a write lands.

So the in-place palette patch is dead: /usr/share/app is on a read-only mount
and the palette file lives there.  Staging the patched file on the SD card would
also not help, because global.xdb shows the engine opens resources by absolute
/usr/share/app path, not by searching a list of directories.

What this script establishes is the remaining option space, from the same mount
table, without burning further sessions on guesses:

  * which mounts are writable, and how big they are
  * whether /setting (nflasha2, rw vfat) has room for a staged file
  * whether the root can be remounted rw -- which needs the ext2 journal or a
    clean-unmount guarantee, and is a real risk to the boot chain
  * what the supported debug entry points are, from change_mode.sh, since
    LD_PRELOAD and gdbserver both work off writable /setting and need no
    resource-format work at all

The honest summary of the palette route: the container is decoded, the patch is
built and verified, the target file is located by inode, and the filesystem
permits the write -- but the mount is read-only, so a stock camera will not
accept the file.  It needs one of:

  A. remount /usr rw          risky: ext2 without a journal, the whole UI
                               lives there, and a failure bricks the UI
  B. write the partition image offline and reflash nflasha15
  C. an overlay/bind mount     needs privileges we may not have
  D. a supported debug path    LD_PRELOAD or gdbserver, via /setting
  E. logo.bin instead          same ro problem -- also on /usr
"""
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(r'D:\02_Development_And_Projects\pmca-re')

MOUNTS = """
rootfs / rootfs rw 0 0
proc /proc proc rw,relatime 0 0
/dev/nflasha7 / ext2 ro,relatime,errors=continue 0 0
/dev/nflasha15 /usr ext2 ro,relatime,errors=continue 0 0
/dev/nflasha10 /tmp vfat rw,sync,dirsync,noatime,fmask=0022,dmask=0022,codepage=cp437,iocharset=ascii,shortname=mixed,posix_attr,avoid_dlink,errors=remount-ro 0 0
/dev/nflasha10 /etc vfat rw,sync,dirsync,noatime,fmask=0022,dmask=0022,codepage=cp437,iocharset=ascii,shortname=mixed,posix_attr,avoid_dlink,errors=remount-ro 0 0
/dev/nflasha3 /system vfat rw,sync,dirsync,noatime,fmask=0022,dmask=0022,codepage=cp437,iocharset=ascii,shortname=mixed,posix_attr,avoid_dlink,errors=remount-ro 0 0
/dev/nflasha2 /setting vfat rw,sync,dirsync,noatime,fmask=0022,dmask=0022,codepage=cp437,iocharset=ascii,shortname=mixed,posix_attr,avoid_dlink,errors=remount-ro 0 0
/dev/nflasha18 /lens vfat rw,sync,dirsync,noatime,fmask=0022,dmask=0022,codepage=cp437,iocharset=ascii,shortname=mixed,posix_attr,avoid_dlink,errors=remount-ro 0 0
/dev/nflasha12 /cert vfat rw,dirsync,noatime,fmask=0022,dmask=0022,codepage=cp437,iocharset=ascii,shortname=mixed,batch_sync,posix_attr,avoid_dlink,errors=remount-ro 0 0
/dev/nflasha11 /log vfat rw,dirsync,noatime,fmask=0022,dmask=0022,codepage=cp437,iocharset=ascii,shortname=mixed,batch_sync,posix_attr,avoid_dlink,errors=remount-ro 0 0
none /sys sysfs rw,relatime 0 0
none /dev/pts devpts rw,relatime,mode=600 0 0
none /tmp_ipsec tmpfs rw,sync,dirsync,noatime,size=128k 0 0
none /tmp_network tmpfs rw,sync,dirsync,noatime,size=1024k 0 0
none /tmp_bt tmpfs rw,sync,dirsync,noatime,size=1024k 0 0
"""

# partition sizes in bytes, from the raw images on the card
SIZES = {
    'nflasha1': 8323072, 'nflasha2': 20971520, 'nflasha3': 50331648,
    'nflasha4': 12582912, 'nflasha5': 62914560, 'nflasha6': 16777216,
    'nflasha7': 8388608, 'nflasha10': 12582912, 'nflasha11': 524288000,
    'nflasha12': 41943040, 'nflasha13': 4194304, 'nflasha15': 314572800,
    'nflasha16': 146800640, 'nflasha17': 104857600, 'nflasha18': 20971520,
    'nflasha23': 67108864,
}

RO_MOUNTS = ('/', '/usr')


def parse():
    out = []
    for line in MOUNTS.strip().splitlines():
        f = line.split()
        if len(f) < 4:
            continue
        dev, mnt, typ, opts = f[0], f[1], f[2], f[3]
        out.append(dict(dev=dev, mnt=mnt, type=typ, opts=opts.split(',')))
    return out


def main():
    ms = parse()
    print('=== writability by mount ===')
    print('%-16s %-10s %-5s %s' % ('device', 'mount', 'rw?', 'size'))
    print('-' * 70)
    for m in ms:
        rw = any(o == 'rw' for o in m['opts'])
        size = ''
        k = m['dev'].split('/')[-1]
        if k in SIZES:
            size = '%8.1f MB' % (SIZES[k] / 1048576)
        print('%-16s %-10s %-5s %s'
              % (m['dev'], m['mnt'], 'yes' if rw else 'NO', size))

    print()
    ro = [m['mnt'] for m in ms if m['mnt'] in RO_MOUNTS]
    print('READ-ONLY mounts: %s' % ', '.join(ro))
    print('  /usr holds /usr/share/app, so the palette file is on a ro mount.')
    print('  / is ro too, and /usr/share depends on it.')

    print()
    print('=== writable space we could stage into ===')
    for m in ms:
        if not any(o == 'rw' for o in m['opts']):
            continue
        if m['type'] not in ('vfat', 'tmpfs'):
            continue
        k = m['dev'].split('/')[-1]
        sz = SIZES.get(k, 0)
        note = ''
        if m['type'] == 'tmpfs':
            s = [o for o in m['opts'] if o.startswith('size=')]
            note = ' %s (RAM only, lost on reboot)' % (s[0] if s else '')
        print('  %-10s %-8s %8.1f MB%s' % (m['mnt'], m['type'], sz / 1048576, note))

    print()
    print('=== the supported debug paths (from /usr/bin/change_mode.sh) ===')
    print('  These work off writable /setting and need no resource-format work.')
    print('    3s  gdbserver        /setting/mode/dmode = 3s')
    print('    3g  target gdb       /setting/mode/dmode = 3g')
    print('    3p  LD_PRELOAD       /setting/mode/preload = <lib path>')
    print('    3L  LeakTracer       preload /usr/tool/LeakTracer.so')
    print('    3e  ElectricFence    preload /usr/tool/libefence.so')
    print('    3f  jemalloc         preload /usr/tool/libjemalloc_tsh.so')
    print('  Preload only affects processes that start after the file is set and')
    print('  the camera reboots, and needs a .so built for this exact ABI.')

    print()
    print('=== assessment of the options ===')
    print("  A. remount /usr rw   NOT ADVISED. ext2 with no journal, the entire")
    print("                       UI lives on it, and a write fault during a")
    print("                       remount leaves the camera unbootable. This is")
    print("                       the one option that can brick the device.")
    print("  B. reflash nflasha15  Viable: we have the full 300 MB image and the")
    print("                       5-byte patch, and it is a single-partition")
    print("                       file edit with an exact restore. Needs a")
    print("                       working write path to the partition.")
    print("  C. bind/overlay       needs privileges the service shell may not")
    print("                       have, and would not survive a reboot anyway.")
    print("  D. LD_PRELOAD/gdb     lowest risk to the device, but we would be")
    print("                       writing and debugging our own .so, which is")
    print("                       back to the hard problem rather than the")
    print("                       clean resource edit.")
    print("  E. logo.bin swap      same ro problem: it is on /usr too.")


if __name__ == '__main__':
    main()
