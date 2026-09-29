#!/usr/bin/env python3
"""Deep 0x98xx probe for the Sony DSC W830 via pmca libusb driver.

Hypothesis to test: 0x9805(arg) returns a uint32 that may be an
"is-this-opcode-supported" or capability accessor. We feed it:
  - arg = standard/vendor opcodes (does it return 1 for supported ops?)
  - wide arg values (powers of 2) to map the value space
  - 2-arg (idx, len) forms to see if 'len' changes returned bytes
Plus tolerant-read 0x9801/0x9802/0x9803 with various args.

Tolerant read captures DATA+RESP; never crashes on type. One run per plug.
"""
import sys, json
from pmca.commands import usb as cu
from pmca.usb import MtpDevice
from pmca.usb.driver.generic import MtpDriver

import pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]

TNAME = {1:'CMD',2:'DATA',3:'RESP'}

JSON_PATH = (REPO / 'ptp_deep_results.json').as_posix()
RES = {'op_9805': {}, 'op_9801': {}, 'op_9802': {}, 'op_9803': {}}

def tolerant(drv, code, args, max_packets=3):
    drv._writeInitialCommand(code, args)
    packets = []
    for _ in range(max_packets):
        try:
            t, c, tx, d = drv._readPtp()
        except Exception as e:
            packets.append({'read_error': repr(e)}); break
        packets.append({'type': t, 'type_name': TNAME.get(t,'?'),
                        'code': c, 'payload_hex': d.hex()})
        if t == 3: break
    return packets

def val_of(pk):
    dp = next((p for p in pk if p.get('type')==2), None)
    if dp and dp.get('payload_hex'):
        raw = bytes.fromhex(dp['payload_hex'])
        return {'value': int.from_bytes(raw,'little'), 'len': len(raw), 'hex': dp['payload_hex']}
    return {'value': None, 'len': 0, 'hex': None}

def main():
    with cu.importDriver('libusb') as driver:
        found = list(driver.listDevices(cu.SONY_ID_VENDOR))
        if not found:
            print('No Sony device (libusb).'); return
        dev, typ, drv = found[0]
        cam = MtpDevice(drv)
        try:
            # 1) 0x9805 with opcodes as arg
            for op in (0x1001,0x1002,0x1004,0x1005,0x1007,0x1008,0x1009,0x100a,
                       0x1014,0x1015,0x101b,0x9801,0x9802,0x9803,0x9805):
                pk = tolerant(cam.driver, 0x9805, [op])
                RES['op_9805']['arg_op_0x%04x' % op] = val_of(pk)
            # 2) wide arg values
            for a in (0,1,2,3,4,5,6,7,8,0x10,0x20,0x40,0x80,0x100,0x200,
                      0x400,0x800,0x1000,0x2000,0x4000,0x8000):
                pk = tolerant(cam.driver, 0x9805, [a])
                RES['op_9805']['arg_0x%04x' % a] = val_of(pk)
            # 3) 2-arg (idx, len)
            for idx in (1,2,3,4,5):
                for L in (4,16,64,256):
                    pk = tolerant(cam.driver, 0x9805, [idx, L])
                    RES['op_9805']['args_%d_%d' % (idx,L)] = val_of(pk)
            # 4) tolerant-read the other vendor ops
            for op, bucket in ((0x9801,'op_9801'),(0x9802,'op_9802'),(0x9803,'op_9803')):
                for a in ([],[1],[2],[0x100],[0x9805]):
                    pk = tolerant(cam.driver, op, a)
                    RES[bucket]['args_%s' % (a,)] = {
                        'resp_code': next((p.get('code_hex') for p in pk if p.get('type')==3), None),
                        'data': next((p.get('payload_hex') for p in pk if p.get('type')==2), None),
                    }
        except Exception as e:
            import traceback
            RES['fatal'] = traceback.format_exc()
        finally:
            with open(JSON_PATH, 'w') as f:
                json.dump(RES, f, indent=2)
    print('Deep probe -> ptp_deep_results.json')

if __name__ == '__main__':
    main()
