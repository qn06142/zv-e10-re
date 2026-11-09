"""Audit native AIF geometry selection over the firmware's full drive scan."""
import argparse
import json
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('repo', type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.repo / 'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness, MEM

harness = Harness()
object_address = MEM
fixture_owner = MEM + 0x100
slots = {logical: 0x5c + 4 * (logical - 5) for logical in range(5, 13)}
for offset in slots.values():
    harness.put(fixture_owner + offset, 0xa1f00000 + offset)

# Distinct words prove slot selection independently of the all-zero catalog.
for logical in range(256):
    harness.u.mem_write(object_address + 8, bytes([logical]))
    expected = 0xa1f00000 + slots[logical] if logical in slots else 0
    assert harness.run(0x63d234e0, object_address, fixture_owner) == expected

owners = {}
for drive in range(0xba):
    owner = harness.run(0x637a6e88, 0, drive, 0)
    owners.setdefault(owner, []).append(drive)

rows = []
for owner, drives in sorted(owners.items()):
    selected = {}
    for logical, offset in slots.items():
        harness.u.mem_write(object_address + 8, bytes([logical]))
        geometry = harness.run(0x63d234e0, object_address, owner)
        assert geometry == harness.word(owner + offset)
        assert geometry == 0, (hex(owner), logical, hex(geometry))
        selected[str(logical)] = hex(geometry)
    rows.append(dict(owner=hex(owner), drives=[hex(drive) for drive in drives], geometry=selected))

print(json.dumps(dict(
    native_header_lookup='0x637a6e88', native_geometry_selector='0x63d234e0',
    drive_scan_end_exclusive='0xba', drive_lookups=0xba, unique_owners=len(owners),
    selector_fixture_cases=256, native_owner_slot_cases=len(owners) * len(slots),
    slot_offsets={str(logical): hex(offset) for logical, offset in slots.items()},
    firmware_tables_modified=False, rows=rows,
), indent=2))
