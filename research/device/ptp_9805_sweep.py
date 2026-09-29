#!/usr/bin/env python3
"""Focused 0x9805 sweep for the Sony DSC W830 via pmca libusb driver.

0x9805 returns a 32-bit LE value in the DATA phase. Sweep arg0 = 0..20
plus a few 2-arg variants to learn whether the arg selects an index/count.
Tolerant read (captures DATA+RESP). One clean run per plug.
"""
import sys, json
from pmca.commands import usb as cu
from pmca.usb import MtpDevice
from pmca.usb.driver.generic import MtpDriver

ORIG_READ = MtpDriver._readPtp
TNAME = {1:'CMD',2:'DATA',3:'RESP'}

def traced_read(self):
    t, c, tx, d = ORIG_READ(self)
    return t, c, tx, d
MtpDriver._readPtp = traced_read

JSON_PATH = 'C:/Users/Minhsnguhoa/pmca-re/ptp_9805_sweep.json'
RES = {'op': 0x9805, 'results': {}}

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

def main():
    with cu.importDriver('libusb') as driver:
        found = list(driver.listDevices(cu.SONY_ID_VENDOR))
        if not found:
            print('No Sony device (libusb).'); return
        dev, typ, drv = found[0]
        cam = MtpDevice(drv)
        try:
            # liveness: GetDeviceInfo
            di = tolerant(cam.driver, 0x1001, [])
            RES['liveness'] = [p for p in di if p.get('type')==2]
            # sweep arg0 = 0..20
            for a in range(0, 21):
                pk = tolerant(cam.driver, 0x9805, [a])
                data_pkt = next((p for p in pk if p.get('type')==2), None)
                val = int.from_bytes(bytes.fromhex(data_pkt['payload_hex']), 'little') if data_pkt and data_pkt.get('payload_hex') else None
                RES['results']['arg_%d' % a] = {'value': val, 'hex': data_pkt['payload_hex'] if data_pkt else None, 'packets': len(pk)}
            # 2-arg variants
            for a in ([1,0x100],[2,0x200],[3,0x300]):
                pk = tolerant(cam.driver, 0x9805, a)
                data_pkt = next((p for p in pk if p.get('type')==2), None)
                val = int.from_bytes(bytes.fromhex(data_pkt['payload_hex']), 'little') if data_pkt and data_pkt.get('payload_hex') else None
                RES['results']['args_%s' % a] = {'value': val, 'hex': data_pkt['payload_hex'] if data_pkt else None}
        except Exception as e:
            import traceback
            RES['fatal'] = traceback.format_exc()
        finally:
            with open(JSON_PATH, 'w') as f:
                json.dump(RES, f, indent=2)
    print('0x9805 sweep -> ptp_9805_sweep.json')

if __name__ == '__main__':
    main()
