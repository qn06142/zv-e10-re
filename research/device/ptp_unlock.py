#!/usr/bin/env python3
"""Unlock-sequence probe for the Sony DSC W830 (libusb/WinUSB).

Hypothesis: the Fujitsu file-transfer opcodes (0x9806..0x981F) are rejected
(0x2005) until some vendor "unlock" handshake runs. We try a few ordered
handshake variants, then re-scan 0x9806..0x981F after each and watch for any
op that flips from 0x2005 to a DATA/handle response.

One clean run per plug. -d libusb. Never CloseSession.
"""
import sys, json
from pmca.commands import usb as cu
from pmca.usb import MtpDevice
from pmca.usb.driver.generic import MtpDriver

TNAME = {1:'CMD',2:'DATA',3:'RESP'}
JSON_PATH = 'C:/Users/Minhsnguhoa/pmca-re/ptp_unlock_results.json'
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

            # Variant A: 0x9801([1]) then 0x9805([1])
            RES['steps']['A_9801_9805'] = {
                '9801': tolerant(cam.driver, 0x9801, [1]),
                '9805': tolerant(cam.driver, 0x9805, [1]),
                'rescan': scan_ext(cam.driver),
            }

            # Variant B: 0x9805([1]) then 0x9803([1])
            RES['steps']['B_9805_9803'] = {
                '9805': tolerant(cam.driver, 0x9805, [1]),
                '9803': tolerant(cam.driver, 0x9803, [1]),
                'rescan': scan_ext(cam.driver),
            }

            # Variant C: 0x9802 with a guess handle 0x20000001
            RES['steps']['C_9802_handle'] = {
                '9802': tolerant(cam.driver, 0x9802, [0x20000001]),
                'rescan': scan_ext(cam.driver),
            }
        except Exception as e:
            import traceback
            RES['fatal'] = traceback.format_exc()
        finally:
            with open(JSON_PATH, 'w') as f:
                json.dump(RES, f, indent=2)
    print('Unlock probe -> ptp_unlock_results.json')

if __name__ == '__main__':
    main()
