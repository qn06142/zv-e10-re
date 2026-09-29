#!/usr/bin/env python3
"""Tolerant PTP/MTP packet tracer for the Sony DSC W830 via pmca's libusb driver.

The W830 uses NON-STANDARD framing: it returns op payloads in the RESPONSE
packet (type 0x3), not a separate DATA packet (type 0x2). pmca's
sendReadCommand strictly expects DATA then RESPONSE, so it throws
'Wrong response type: 0x3'. This tracer monkeypatches MtpDriver to capture
EVERY packet regardless of type, and drives ops with a tolerant reader that
returns all packets received for a command.

ONE clean run per USB plug. No CloseSession (wedges). Replug before re-running.
"""
import sys, json
from pmca.commands import usb as cu
from pmca.usb import MtpDevice
from pmca.usb.driver.generic import MtpDriver

import pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]

CAP = []
ORIG_WRITE = MtpDriver._writePtp
ORIG_READ = MtpDriver._readPtp
TNAME = {1: 'CMD', 2: 'DATA', 3: 'RESP'}

def traced_write(self, type, code, transaction, data=b''):
    CAP.append({'dir': 'OUT', 'type': type, 'type_name': TNAME.get(type, '?'),
                'code': code, 'code_hex': hex(code), 'txn': transaction,
                'payload_hex': data.hex() if data else ''})
    return ORIG_WRITE(self, type, code, transaction, data)

def traced_read(self):
    type, code, transaction, data = ORIG_READ(self)
    CAP.append({'dir': 'IN', 'type': type, 'type_name': TNAME.get(type, '?'),
                'code': code, 'code_hex': hex(code), 'txn': transaction,
                'payload_hex': data.hex() if data else ''})
    return type, code, transaction, data

MtpDriver._writePtp = traced_write
MtpDriver._readPtp = traced_read

JSON_PATH = (REPO / 'ptp_trace_results.json').as_posix()
RES = {'device': 'Sony DSC W830', 'ops': {}}

def tolerant_read(drv, code, args, max_packets=3):
    """Send a command, then read up to max_packets packets (any type), return
    a list of {type, code, payload}. Mirrors what the camera actually sends."""
    try:
        drv._writeInitialCommand(code, args)
    except Exception as e:
        return {'error': 'write: %r' % e, 'packets': []}
    packets = []
    for _ in range(max_packets):
        try:
            t, c, tx, d = drv._readPtp()
        except Exception as e:
            packets.append({'read_error': repr(e)})
            break
        packets.append({'type': t, 'type_name': TNAME.get(t, '?'),
                        'code': c, 'code_hex': hex(c), 'payload_hex': d.hex()})
        # stop if we got a RESPONSE (type 3) - that's the normal terminator
        if t == 3:
            break
    return {'packets': packets}

def main():
    with cu.importDriver('libusb') as driver:
        found = list(driver.listDevices(cu.SONY_ID_VENDOR))
        if not found:
            print('No Sony device found (libusb).'); return
        dev, typ, drv = found[0]
        cam = MtpDevice(drv)   # opens one session
        try:
            # GetDeviceInfo via tolerant read (it returns type 3, not 2)
            RES['deviceinfo'] = tolerant_read(cam.driver, 0x1001, [], 3)
            for op in (0x9801, 0x9802, 0x9803, 0x9805):
                RES['ops']['op_0x%04x' % op] = {}
                for nargs in (0, 1, 2):
                    for argvals in ([], [1], [1, 0x200]):
                        a = argvals[:nargs] if nargs else []
                        key = 'nargs%d_%s' % (nargs, a)
                        RES['ops']['op_0x%04x' % op][key] = tolerant_read(cam.driver, op, a, 3)
            RES['captured_packets'] = CAP
        except Exception as e:
            import traceback
            RES['fatal'] = traceback.format_exc()
        finally:
            with open(JSON_PATH, 'w') as f:
                json.dump(RES, f, indent=2)
    print('Trace complete -> ptp_trace_results.json (%d packets)' % len(CAP))

if __name__ == '__main__':
    main()
