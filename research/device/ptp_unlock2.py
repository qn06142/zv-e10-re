#!/usr/bin/env python3
"""Longer unlock-sequence probe for the Sony DSC W830 (libusb/WinUSB).

The simple handshake (0x9801+0x9805) only woke 0x9808/0x9809 (status flags).
This variant tries a longer ordered sequence, then re-scans 0x9806..0x981F to
see if any op flips from rejected (0x2005) to a DATA/handle response.

One clean run per plug. -d libusb. Never CloseSession.
"""
import sys, json
from pmca.commands import usb as cu
from pmca.usb import MtpDevice
from pmca.usb.driver.generic import MtpDriver

import pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]

TNAME = {1:'CMD',2:'DATA',3:'RESP'}
JSON_PATH = (REPO / 'ptp_unlock2_results.json').as_posix()
RES = {'steps': {}}

def tolerant(drv, code, args, max_packets=3):
    drv._writeInitialCommand(code, args)
    packets = []
    for _ in range(max_packets):
        try:
            t, c, tx, d = drv._readPtp()
        except Exception as e:
            packets.append({'read_error': repr(e)}); break
        packets.append({'type': t, 'type_name': TNAME.get(t,'?'),
                        'code': c, 'code_hex': hex(c), 'payload_hex': d.hex()})
        if t == 3: break
    return packets

def resp_of(pk):
    r = next((p for p in pk if p.get('type')==3), None)
    return r['code_hex'] if r else None

def data_of(pk):
    d = next((p for p in pk if p.get('type')==2), None)
    return d['payload_hex'] if (d and d.get('payload_hex')) else None

def scan_ext(drv):
    out = {}
    for op in range(0x9806, 0x9820):
        pk = tolerant(drv, op, [1])
        out['op_0x%04x' % op] = {'resp': resp_of(pk), 'data': data_of(pk)}
    return out

def main():
    with cu.importDriver('libusb') as driver:
        found = list(driver.listDevices(cu.SONY_ID_VENDOR))
        if not found:
            print('No Sony device (libusb).'); return
        dev, typ, drv = found[0]
        cam = MtpDevice(drv)
        try:
            RES['baseline_scan'] = scan_ext(cam.driver)

            # Longer handshake: 0x9801, 0x9805, 0x9803, 0x9805
            RES['steps']['LONG_handshake'] = {
                's1_9801': tolerant(cam.driver, 0x9801, [1]),
                's2_9805': tolerant(cam.driver, 0x9805, [1]),
                's3_9803': tolerant(cam.driver, 0x9803, [1]),
                's4_9805': tolerant(cam.driver, 0x9805, [1]),
                'rescan': scan_ext(cam.driver),
            }

            # Alternate: 0x9805, 0x9801, 0x9805, 0x9803, 0x9805
            RES['steps']['ALT_handshake'] = {
                's1_9805': tolerant(cam.driver, 0x9805, [1]),
                's2_9801': tolerant(cam.driver, 0x9801, [1]),
                's3_9805': tolerant(cam.driver, 0x9805, [1]),
                's4_9803': tolerant(cam.driver, 0x9803, [1]),
                's5_9805': tolerant(cam.driver, 0x9805, [1]),
                'rescan': scan_ext(cam.driver),
            }
        except Exception as e:
            import traceback
            RES['fatal'] = traceback.format_exc()
        finally:
            with open(JSON_PATH, 'w') as f:
                json.dump(RES, f, indent=2)
    print('Long unlock probe -> ptp_unlock2_results.json')

if __name__ == '__main__':
    main()
