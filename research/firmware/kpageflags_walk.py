"""Resolve a kernel VA to a physical address using /proc/kpageflags.

Why this route
--------------
Three earlier routes are now closed, each verified:

  * /dev/mem at page size -- the kernel text PA 0x108000 returns a 0-byte
    read even with bs=4096, so the read-only kernel mapping is not reachable
    through /dev/mem on this device.
  * /dev/mem below page size -- returns a 0-byte file with NO error at all.
  * page tables -- the kernel does not export swapper_pg_dir or page_offset
    (kallsyms returns nothing for them), and the VA->PA offset cannot be
    inferred: 0x5F00A000 falls below a 3:1 split (0xC0000000) and below a 2:2
    split (0x80000000), and iomem names only System RAM at 0x0-0x3FFFFFFF and
    0x80000000-0x8FFFFFFF, neither of which contains it.

/proc/kpageflags is the remaining lever and it is root-readable here.  It is a
bitmap with one bit per physical page; a set bit means the page is mapped, and
the bit index IS the physical address.  So for a target VA we can:

  1. read /proc/kpagecount to learn how many pages to scan
  2. read /proc/kpageflags in chunks
  3. for each set bit, treat that physical address as a candidate and test
     whether the bytes there look like the expected code

Testing "does it look like ldec's code" needs a reference, and we have one:
ldec_probe is a real function at module+0xC0, and the module is a contiguous
~46 KB of ARM code.  A candidate page whose first words decode as a plausible
ARM prologue (push/stmdb, or a literal-pool load) and which sits in a run of
such pages is the module.

This is a READ-ONLY enumeration: no writes, no ioctls, nothing the driver can
object to.  It is the safe counterpart to the ioctl sweep that wedged the
session.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# --- reference: what ldec's first function should look like ---------------
# From kallsyms: ldec_open 0x5F00A014, ldec_close 0x5F00A028, ldec_probe
# 0x5F00A0C0.  A module's .text usually begins with a few bytes of header or
# jumps straight into a function.  A valid ARM prologue is one of:
#   E92D....  stmdb sp!, {...}     (32-bit push.w)
#   B5..      push {..,lr}         (16-bit push)
#   E1A0..    mov r0, r0           (nop / alignment)
#   E59F..    ldr pc, [pc, #..]    (literal return)
PROLOGUE_PREFIXES = (0xE92D, 0xE1A0, 0xE59F, 0xE28F, 0xE52D)


def looks_like_code(buf):
    """Weak test: do the first few 32-bit words look like ARM instructions?"""
    hits = 0
    for i in range(0, min(len(buf), 32), 4):
        w = struct.unpack_from('<I', buf, i)[0]
        if (w >> 16) in PROLOGUE_PREFIXES:
            hits += 1
        # a 16-bit Thumb push is 0xB5xx in the low half with the high half
        # being the next instruction
        if i + 2 <= len(buf):
            hw = struct.unpack_from('<H', buf, i)[0]
            if (hw & 0xFF00) == 0xB500:
                hits += 1
    return hits


def scan_flags(flags_blob, first_page=0):
    """Yield the physical addresses of every set bit in a kpageflags chunk."""
    for byte_i, byte in enumerate(flags_blob):
        if not byte:
            continue
        for bit in range(8):
            if byte & (1 << bit):
                yield (first_page + byte_i * 8 + bit) * 4096


if __name__ == '__main__':
    print(__doc__)
    print('This module is the PC-side decoder.  The camera-side helper reads')
    print('/proc/kpageflags and /dev/mem at page size to test candidates.')
    print()
    print('Prologue prefixes accepted: %s'
          % ', '.join('0x%04X' % p for p in PROLOGUE_PREFIXES))
    if len(sys.argv) > 1:
        buf = Path(sys.argv[1]).read_bytes()
        print('\n%s: %d bytes, looks_like_code -> %d hits'
              % (sys.argv[1], len(buf), looks_like_code(buf)))
