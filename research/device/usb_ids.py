#!/usr/bin/env python3
"""
usb_ids.py - read USB string descriptors (iManufacturer, iProduct,
iSerialNumber) for every Sony (VID_054C) device currently attached, and list
all Sony PIDs seen. The iSerialNumber is the per-unit "USB Serial No." that the
service manual says Adjust Station writes -- readable here WITHOUT service mode
on a working camera. Enumerate-only, non-destructive.
"""
import usb.core, usb.util, json, sys

VID = 0x054c
JSON_PATH = 'C:/Users/Minhsnguhoa/pmca-re/usb_ids_results.json'
RES = {'devices': [], 'all_sony_pids': []}

def eprint(*a):
    print(*a); sys.stdout.flush()

devs = usb.core.find(find_all=True)
sony = [d for d in devs if d.idVendor == VID]
eprint('Sony devices found: %d' % len(sony))
for d in sony:
    entry = {'pid': '0x%04X' % d.idProduct}
    RES['all_sony_pids'].append(d.idProduct)
    try:
        # string descriptors (index 1=manufacturer,2=product,3=serial)
        try:
            d.set_configuration()
        except NotImplementedError:
            pass
        for idx, key in ((1, 'iManufacturer'), (2, 'iProduct'), (3, 'iSerialNumber')):
            try:
                s = usb.util.get_string(d, idx)
            except Exception as e:
                s = 'ERR:%r' % e
            entry[key] = s
        entry['bcdDevice'] = '0x%04X' % d.bcdDevice
        entry['bDeviceClass'] = '0x%02X' % d.bDeviceClass
    except Exception as e:
        entry['error'] = repr(e)
    RES['devices'].append(entry)
    eprint('  PID %s: %s' % (entry['pid'], {k: v for k, v in entry.items() if k != 'pid'}))

try:
    with open(JSON_PATH, 'w') as f:
        json.dump(RES, f, indent=2)
    eprint('USB IDs -> %s' % JSON_PATH)
except Exception as e:
    eprint('write error: %r' % e)
