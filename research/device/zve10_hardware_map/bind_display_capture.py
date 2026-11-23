"""Validate saved read-only display capture; never connects to a camera."""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

BASE = 0x635c6000


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(capture, reference, saved_contracts):
    session = json.loads((capture / 'session.json').read_text())
    settings = json.loads((capture / 'display-backup-units.json').read_text())
    assert session['status'] == 'display-related-files-and-units-read-only'
    assert session['camera_writes'] is False
    assert settings['mode'] == 'Senser'
    identity = next(c for c in session['commands'] if c['command'] == 'busybox cat /proc/uptime /proc/sys/kernel/random/boot_id /proc/version')
    assert identity['rc'] == 0
    boot_id = re.search(r'(?m)^([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\s*$', identity['output'])
    assert boot_id
    for name, identity in session['files'].items():
        path = capture / name
        assert path.stat().st_size == identity['bytes']
        assert digest(path) == identity['sha256']
    image = reference.read_bytes()
    assert hashlib.md5(image).hexdigest() == 'cdcae9d4fdbf66a33704a4c7564e346d'
    current = (capture / 'av-cam.bin').read_bytes()
    comparisons = []
    for region in session['display_code_comparisons']:
        start, end = int(region['file_start'], 0), int(region['file_end_exclusive'], 0)
        assert region['reference_match'] is True and current[start:end] == image[start:end]
        comparisons.append(dict(region, sha256=hashlib.sha256(current[start:end]).hexdigest()))
    units = settings['units']
    def unit(key):
        entry = units[hex(key)]
        data = bytes.fromhex(entry['data_hex'])
        assert len(data) == entry['bytes']
        return data
    assert len(units) == session['backup_units_read'] == 328
    assert unit(0x5f0206) == b'\0', 'Only selector-zero profile mapping has been audited'
    ids = struct.unpack_from('<304I', image, 0x645ecaf0 - BASE)
    assert struct.unpack_from('<I', image, 0x645ecaf0 - BASE + 304*4)[0] == 0
    assert all(len(unit(key)) == 1 for key in ids)
    profile = b''.join(unit(key) for key in ids)
    contracts = json.loads(saved_contracts.read_text())
    assert session['files']['liro.ko']['sha256'] == contracts['liro_sha256']
    assert session['files']['libObj.so']['sha256'] == contracts['libobj_sha256']
    selected = {}
    for key, saved in contracts['selected_saved_backup_properties'].items():
        value = unit(int(key, 0))
        selected[key] = {'bytes': len(value), 'value_le': hex(int.from_bytes(value, 'little')),
                         'matches_saved_backup': len(value) == saved['bytes'] and int.from_bytes(value, 'little') == int(saved['value_le'], 0)}
    bank, bit = (int.from_bytes(unit(key), 'little') for key in (0xf9088f, 0xf90890))
    assert (bank, bit) == (11, 20)
    return {'schema_version': 1, 'capture_date': '2026-11-18', 'mode': 'Senser',
            'boot_id': boot_id.group(1),
            'camera_writes': False, 'camera_access_performed_by_validator': False,
            'source_receipts_sha256': {name: digest(capture / name) for name in ('session.json', 'display-backup-units.json')},
            'camera_files': session['files'], 'reference_firmware_sha256': hashlib.sha256(image).hexdigest(),
            'matched_regions': comparisons, 'backup_units_read': len(units),
            'selected_display_properties': selected,
            'lcd_profile0': {'selector': 0, 'bytes': len(profile), 'source_id_list_va': '0x645ecaf0',
                             'destination_firmware_va': '0x6455fe88', 'sha256': hashlib.sha256(profile).hexdigest(),
                             'matches_saved_backup': hashlib.sha256(profile).hexdigest() == contracts['saved_profile0']['sha256']},
            'pin_slot_2': {'bank': bank, 'bit': bit, 'set_address': '0xf2910b44', 'clear_address': '0xf2910b48',
                           'mask': '0x00100000', 'electrical_role': 'unresolved'},
            'limits': ['Backup configuration was read in Senser mode; no normal-shooting or resident MMIO was captured',
                       'No physical display initialization, clock, routing or pin electrical role was established',
                       'File-slice matches do not imply whole firmware identity or runtime memory identity']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--contracts', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = bind(args.capture, args.reference, args.contracts)
    args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'validated': True, 'units': result['backup_units_read'], 'pin': result['pin_slot_2'],
                      'profile': result['lcd_profile0'], 'selected_properties_match_saved': all(v['matches_saved_backup'] for v in result['selected_display_properties'].values())}))
