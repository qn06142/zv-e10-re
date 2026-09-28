"""Find the PGD physical address via /proc/self/pagemap, then walk it.

Last route for translating ldec's kernel VA to a readable physical address.

What is established (each verified on-camera):
  * /dev/ldec opens from our own code, so the display driver is callable
  * ldec_ioctl is at VA 0x5F00A2E8 (from /proc/kallsyms)
  * PA 0x5F00A000 via /dev/mem returns 0 bytes, so it is a true kernel VA
  * userspace ends at 0x5EFB8000 ([stack] in /proc/self/maps), so the kernel
    window begins just above at 0x5F000000
  * swapper_pg_dir / page_offset are not exported by kallsyms
  * /proc/ldec does not exist

So the kernel page tables must be reached another way.  /proc/self/pagemap is
readable and reports the PHYSICAL frame backing any of OUR OWN virtual
addresses.  Two things follow:

  1. pagemap of our own stack/heap tells us how a VA maps to a PA on this
     machine, which calibrates the descriptor format (short-descriptor vs LPAE).
  2. the PGD itself is reachable: on ARM Linux it is a kernel symbol, but we
     can also locate it by scanning the readable low RAM for a page whose
     contents are a plausible PGD -- mostly zero with a handful of section
     descriptors whose PAs land inside System RAM.

The first is a pure userspace read and is what this helper does first: it
dumps pagemap entries for a set of our own addresses, so the PC can check
whether pagemap returns real PFNs here at all.  Earlier work reported all-zero
pagemap for another process, which may have been a wrong-address artefact
rather than a real negative -- worth re-testing on our own addresses.

Usage: pagemap_probe.py <out.bin>     (camera-side helper is built separately)
"""
import struct
import sys
from pathlib import Path

# Addresses to sample from our own process.  These come from /proc/self/maps
# and are chosen to span the heap, the binary's own text, and the stack, so a
# zero result cannot be dismissed as "that address happens to be unmapped".
SAMPLES = [
    ('stack', 0x5EF97000),
    ('vectors', 0xFFFF0000),
]


def decode_entry(e):
    """Decode one 64-bit pagemap entry."""
    if e == 0:
        return {'present': False}
    present = bool(e & (1 << 63))
    swapped = bool(e & (1 << 62))
    pfn = (e >> 6) & 0xFFFFFFFFFFFFF
    return {
        'present': present,
        'swapped': swapped,
        'pfn': pfn,
        'pa': pfn * 4096,
        'softdirty': bool(e & (1 << 55)),
        'exclusive': bool(e & (1 << 54)),
        'file': bool(e & (1 << 61)),
        'shared': bool(e & 1),
    }


def analyse(blob, base_va, label):
    print('=== %s  base VA 0x%08X ===' % (label, base_va))
    if len(blob) % 8:
        print('  odd length %d -- truncating' % len(blob))
        blob = blob[:len(blob) - (len(blob) % 8)]
    nz = 0
    rows = []
    for i in range(0, len(blob), 8):
        e = struct.unpack_from('<Q', blob, i)[0]
        va = base_va + i
        if e:
            nz += 1
        d = decode_entry(e)
        rows.append((va, e, d))
    print('  %d entries, %d non-zero' % (len(rows), nz))
    for va, e, d in rows[:12]:
        if d.get('present'):
            print('    0x%08x  entry 0x%016X  PA 0x%08X%s%s'
                  % (va, e, d['pa'],
                     '  FILE' if d['file'] else '',
                     '  SWAP' if d['swapped'] else ''))
        elif e:
            print('    0x%08x  entry 0x%016X  (not present)' % (va, e))
    if nz == 0:
        print('  -> ALL ZERO. pagemap is returning nothing useful for these')
        print('     addresses on this kernel; the route is closed.')
    return nz


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    blob = Path(sys.argv[1]).read_bytes()
    total = 0
    for label, va in SAMPLES:
        chunk = blob[:8 * 64]          # 64 entries = 512 bytes per sample
        total += analyse(chunk, va, label)
        print()
    print('RESULT: %d non-zero entries across all samples' % total)
