#!/usr/bin/env python3
"""Scan Fujitsu PTP extension opcodes 0x9806..0x981F on the Sony DSC W830.

Hypothesis: the real object enumerator/transfer op lives in this range (the
4 known vendor ops 0x9801/02/03/05 are just status/flag/reject). We send each
op as a tolerant read (captures DATA+RESPONSE) with a few arg sets and record
the response code + any data bytes. An op returning >4 bytes or a handle list
is the enumerator we want.

One clean run per plug. -d libusb. Never CloseSession.
"""
import sys, json
from pmca.commands import usb as cu
from pmca.usb import MtpDevice
from pmca.usb.driver.generic import MtpDriver

TNAME = {1:'CMD',2:'DATA',3:'RESP'}
JSON_PATH = 'C:/Users/Minhsnguhoa/pmca-re/ptp_scan_ext_results.json'
RES = {'range': '0x9806..0x981F', 'ops': {}}

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

def main():
    with cu.importDriver('libusb') as driver:
        found = list(driver.listDevices(cu.SONY_ID_VENDOR))
        if not found:
            print('No Sony device (libusb).'); return
        dev, typ, drv = found[0]
        cam = MtpDevice(drv)
        try:
            # liveness
            liv = tolerant(cam.driver, 0x1001, [])
            RES['liveness'] = 'ok' if any(p.get('type')==2 for p in liv) else 'WEDGED'
            for op in range(0x9806, 0x9820):
                RES['ops']['op_0x%04x' % op] = {}
                for a in ([], [1], [0x20000001], [1, 256]):
                    pk = tolerant(cam.driver, op, a)
                    resp = next((p for p in pk if p.get('type')==3), None)
                    data = next((p for p in pk if p.get('type')==2), None)
                    RES['ops']['op_0x%04x' % op]['args_%s' % (a,)] = {
                        'resp_code': resp['code_hex'] if resp else None,
                        'data_len': len(data['payload_hex'])//2 if data and data.get('payload_hex') else 0,
                        'data_hex': (data['payload_hex'][:64] if data and data.get('payload_hex') else None),
                    }
        except Exception as e:
            import traceback
            RES['fatal'] = traceback.format_exc()
        finally:
            with open(JSON_PATH, 'w') as f:
                json.dump(RES, f, indent=2)
    print('Extension scan -> ptp_scan_ext_results.json')

if __name__ == '__main__':
    main()
