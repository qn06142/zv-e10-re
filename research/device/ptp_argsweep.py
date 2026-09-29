#!/usr/bin/env python3
"""Probe the now-unlocked vendor ops (0x9806/0x9807/0x9808) with varied args.

Flow: run the working handshake (0x9801,0x9805,0x9803,0x9805) to wake the ops,
then for each awake op sweep a range of arg values and capture the response
code + any DATA bytes. Looking for an arg that makes an op return more than a
4-byte flag (i.e. a handle list or object data) -- the actual enumerator.

One clean run per plug. -d libusb. Gate via run_after_reboot.py.
"""
import sys, json
from pmca.commands import usb as cu
from pmca.usb import MtpDevice
from pmca.usb.driver.generic import MtpDriver

import pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]

TNAME = {1:'CMD',2:'DATA',3:'RESP'}
JSON_PATH = (REPO / 'ptp_argsweep_results.json').as_posix()
RES = {'awake_ops': [0x9806, 0x9807, 0x9808], 'probes': {}}

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

def wake(drv):
    # known cumulative handshake that wakes 0x9806/0x9807/0x9808
    for op, a in ((0x9801,[1]),(0x9805,[1]),(0x9803,[1]),(0x9805,[1])):
        tolerant(drv, op, a)

def main():
    with cu.importDriver('libusb') as driver:
        found = list(driver.listDevices(cu.SONY_ID_VENDOR))
        if not found:
            print('No Sony device (libusb).'); return
        dev, typ, drv = found[0]
        cam = MtpDevice(drv)
        try:
            wake(cam.driver)
            args = (list(range(0, 65)) +
                    [0x10000, 0x20000, 0x20000001, 0x00010001, 0x00020001, 0x01000000])
            for op in RES['awake_ops']:
                RES['probes']['op_0x%04x' % op] = {}
                for a in args:
                    pk = tolerant(cam.driver, op, [a])
                    dhex = data_of(pk)
                    RES['probes']['op_0x%04x' % op]['arg_%d' % a] = {
                        'resp': resp_of(pk),
                        'data_len': len(dhex)//2 if dhex else 0,
                        'data': dhex[:64] if dhex else None,
                    }
        except Exception as e:
            import traceback
            RES['fatal'] = traceback.format_exc()
        finally:
            with open(JSON_PATH, 'w') as f:
                json.dump(RES, f, indent=2)
    print('Arg-sweep -> ptp_argsweep_results.json')

if __name__ == '__main__':
    main()
