"""Walk the ARM page tables to translate a kernel VA to a physical address.

Why this is needed
------------------
/proc/kallsyms gives ldec's symbols authoritatively:

    5f00a2e8 t ldec_ioctl
    5f00a03c T boss_lld_get_base_addr_ldec
    5f00afbc T boss_hw_ldec_set

But those are VIRTUAL addresses and there is no way to infer the VA->PA
mapping for this SoC:

  * a 3:1 split would put kernel at 0xC0000000+, and 0x5F00A000 is below that
  * a 2:2 split would put kernel at 0x80000000+, and 0x5F00A000 is below that too
  * iomem shows kernel text at PA 0x00108000-0x00495023, which is a third
    window entirely

So the offset has to be read, not deduced.  The page tables are reachable from
userspace on this kernel: /proc/self/pagemap plus the TTBR globals, and
/proc/kallsyms exposes the `swapper_pg_dir` / `page_offset` symbols needed to
find the tables without guessing at the split.

This script runs PC-side and decodes the answers; the camera-side reader is a
small helper that dumps whatever the walk needs.  Keeping the decode here means
the reasoning is checkable without burning a camera session.
"""
import struct
import sys
from pathlib import Path

# ARM short-descriptor page table entry bits
def pte_is_valid(pte):
    return (pte & 3) != 0 and (pte & 3) != 1        # 1 = reserved


def pte_is_page(pte):
    """2 = section, 3 = page.  Only a 'page' entry (pte & 3 == 3) has a PA."""
    return (pte & 3) == 3


def pte_to_pa(pte):
    return pte & 0xFFFFF000


def coarse_pte_to_pa(pte):
    """Coarse (second-level) page table entry: PA is in bits 30:8."""
    return (pte & 0xFFFFFC00) << 2


def fine_pte_to_pa(pte):
    return pte & 0xFFFFF000


def translate(va, pgd_pa, tables):
    """Translate a VA using section/ coarse/ fine descriptors.

    tables: dict mapping a physical page address to its 1024 bytes of entries.
    Returns (pa, level) or (None, reason).
    """
    # outer level: this kernel is 2-level (section at level 1)
    pgd_index = (va >> 30) & 0x3
    entry = tables.get(pgd_pa, b'')[pgd_index * 4:pgd_index * 4 + 4]
    if len(entry) < 4:
        return None, 'no PGD entry (pgd_pa=0x%08x)' % pgd_pa
    pte = struct.unpack_from('<I', entry)[0]
    if not pte_is_valid(pte):
        return None, 'PGD entry invalid (0x%08X)' % pte
    if pte_is_page(pte):
        return pte_to_pa(pte) + (va & 0xFFF), 'outer PAGE (1-level map)'

    table_pa = coarse_pte_to_pa(pte) & 0xFFFFF000
    sec_index = (va >> 20) & 0xFFF
    entry2 = tables.get(table_pa, b'')[sec_index * 4:sec_index * 4 + 4]
    if len(entry2) < 4:
        return None, 'no section entry at 0x%08x' % table_pa
    pte2 = struct.unpack_from('<I', entry2)[0]
    if not pte_is_valid(pte2):
        return None, 'section entry invalid (0x%08X)' % pte2
    if pte_is_page(pte2):
        return fine_pte_to_pa(pte2) + (va & 0xFFF), 'fine PAGE'
    if (pte2 & 3) == 2:
        # SECTION: base is bits 31:20, 1MB granularity
        return ((pte2 & 0xFFF00000) | (va & 0xFFFFF)), 'SECTION (1MB)'
    return None, 'unexpected descriptor 0x%08X' % pte2


TARGETS = {
    'ldec_ioctl': 0x5F00A2E8,
    'ldec module base': 0x5F00A000,
    'boss_lld_get_base_addr_ldec': 0x5F00A03C,
}

if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv) > 1 else None
    if not src:
        print(__doc__)
        print('Targets to translate:')
        for k, v in TARGETS.items():
            print('   %-28s 0x%08X' % (k, v))
        print('\nUsage: pagewalk.py <dumped_tables.bin> <pgd_pa_hex>')
        sys.exit(0)

    blob = Path(src).read_bytes()
    pgd_pa = int(sys.argv[2], 0) if len(sys.argv) > 2 else None
    if pgd_pa is None:
        print('need the PGD physical address as the second argument')
        sys.exit(2)
    tables = {pgd_pa: blob[:4096]}
    off = 4096
    while off + 4096 <= len(blob):
        tables[off] = blob[off:off + 4096]
        off += 4096

    print('=== VA -> PA translation (pgd_pa = 0x%08X) ===' % pgd_pa)
    for name, va in TARGETS.items():
        pa, why = translate(va, pgd_pa, tables)
        if pa is None:
            print('  %-28s 0x%08X -> FAILED: %s' % (name, va, why))
        else:
            print('  %-28s 0x%08X -> PA 0x%08X   (%s)' % (name, va, pa, why))
