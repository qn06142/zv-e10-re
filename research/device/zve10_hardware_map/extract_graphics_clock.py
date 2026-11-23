"""Recover an offline graphics clock-up transaction from the identified Sony module.

No camera access, execution or proposed write trial. Addresses/values retain binary scope.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from elftools.elf.elffile import ELFFile


def extract(path):
    raw = path.read_bytes()
    identity = hashlib.sha256(raw).hexdigest()
    if identity != '4e4b99e5e17e170ddc13dc432178299512525debd6fb19512521b38867da7a65':
        raise ValueError('Unreviewed grm_gles.ko identity')
    with path.open('rb') as f:
        elf = ELFFile(f)
        text = elf.get_section_by_name('.text').data()
        symtab = elf.get_section_by_name('.symtab')
        refs = {r['r_offset']: symtab.get_symbol(r['r_info_sym']).name
                for r in elf.get_section_by_name('.rel.text').iter_relocations()}
    word = lambda a: struct.unpack_from('<I', text, a)[0]
    # Reviewed A32 constants and masks; these are section offsets, not file offsets.
    for a, expected in {0x260: 0xe3c0000f, 0x264: 0xe3800006,
                        0x278: 0xe3c0000f, 0x27c: 0xe3800006,
                        0x290: 0xe3c0000f, 0x294: 0xe3800006,
                        0x2a8: 0xe3c0000f, 0x2ac: 0xe3800006,
                        0x2b8: 0xe3a00015, 0x2c8: 0xe3a00010,
                        0x2dc: 0xe3500015}.items():
        assert word(a) == expected, hex(a)
    for a in (0x258, 0x270, 0x288, 0x2a0, 0x2d8): assert refs[a] == 'sugilite_ioread32'
    for a in (0x268, 0x280, 0x298, 0x2b0, 0x2bc, 0x2d0): assert refs[a] == 'sugilite_iowrite32'
    assert refs[0x2c4] == '__const_udelay' and refs[0x2e4] == '__bug_noarg'
    addresses = [word(a) for a in (0x2f0, 0x2f4, 0x2f8, 0x2fc)]
    assert addresses == [0xf28040c4, 0xf28041a8, 0xf28050b8, 0xf280518c]
    assert word(0x300) == 0xf3400080 and word(0x308) == 0xf3400280
    sequence = [{'operation': 'read_modify_write32', 'address_space': 'physical_mmio',
                 'address': hex(a), 'clear_mask': '0xf', 'set_bits': '0x6',
                 'preserve': 'all other bits'} for a in addresses]
    sequence += [
        {'operation': 'write32', 'address': '0xf3400080', 'value': '0x15'},
        {'operation': 'call_delay', 'function': '__const_udelay', 'raw_argument': hex(word(0x304)),
         'wall_clock_duration_verified': False},
        {'operation': 'write32', 'address': '0xf3400280', 'value': '0x10'},
        {'operation': 'read32_and_compare', 'address': '0xf3400080', 'expected_equal': '0x15',
         'on_match': 'return', 'on_mismatch': '__bug_noarg', 'polling_loop': False}]
    return {'schema_version': 1, 'kind': 'source-derived transaction, not an executable recipe',
            'subsystem': 'Sugilite graphics clock-up', 'source_module': 'grm_gles.ko',
            'source_sha256': identity, 'function': 'sugilite_clock_up_internal',
            'section': '.text', 'section_offset': '0x248',
            'current_camera_module_identity_checked': False, 'hardware_transaction_verified': False,
            'camera_access_performed': False, 'read_or_write_permission': False,
            'io_helpers': {'read32': 'direct LDR then DSB SY',
                           'write32': 'DSB SY, optional outer_cache callback at struct offset 0x1c, then direct STR'},
            'sequence': sequence,
            'limits': ['Inputs/prerequisites and shared clock ownership not fully recovered',
                       'Expected 0x15 applies only after this source transaction; not a reset default',
                       'No panel power/timing/routing or sensor initialization is supplied',
                       'Addresses are directly dereferenced by this module; actual device mapping/body state still requires binding']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--module', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); result = extract(a.module)
    a.out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'status': 'identified-module-opcodes-and-relocations-checked',
                      'ordered_steps': len(result['sequence']), 'camera_access_performed': False}))
