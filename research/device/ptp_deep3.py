#!/usr/bin/env python3
"""
Deep3: BIG handshake burst to maximize the cumulative vendor unlock, then
enumerate EVERYTHING and arg-probe the awake ops -- all in one clean session.

Hypothesis: the unlock is a per-session counter advanced by handshake ops. A
large burst should wake 0x9810..0x981f (and beyond), and the file-transfer
enumerator is among the highest woken ops, possibly taking an arg.

Single session per plug. -d libusb.
"""
import sys, json
from pmca.commands import usb as cu
from pmca.usb import MtpDevice
from pmca.usb.driver.generic import MtpDriver

TNAME = {1:'CMD',2:'DATA',3:'RESP'}
JSON_PATH = 'C:/Users/Minhsnguhoa/pmca-re/ptp_deep3_results.json'
BURST = 16
RES = {'burst_cycles': BURST, 'fullscan': {}, 'argprobe': {}}

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

def burst(drv, n):
    for _ in range(n):
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
            burst(cam.driver, BURST)
            # full rescan 0x9801..0x9820
            for op in range(0x9801, 0x9820):
                pk = tolerant(cam.driver, op, [1])
                RES['fullscan']['op_0x%04x' % op] = {
                    'resp': resp_of(pk),
                    'data_len': len(data_of(pk) or '')//2,
                    'data': (data_of(pk)[:64] if data_of(pk) else None),
                }
            # arg-probe every op that returned 0x2001 (awake) in fullscan
            awake = [op for op in range(0x9801, 0x9820)
                     if RES['fullscan']['op_0x%04x' % op]['resp'] == '0x2001']
            RES['awake_list'] = ['op_0x%04x' % o for o in awake]
            args = list(range(0, 17)) + [0xFFFFFFFF, 0x00020001, 0x00010001]
            for op in awake:
                RES['argprobe']['op_0x%04x' % op] = {}
                for a in args:
                    pk = tolerant(cam.driver, op, [a])
                    dhex = data_of(pk)
                    RES['argprobe']['op_0x%04x' % op]['arg_%d' % a] = {
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
    print('Deep3 burst probe -> ptp_deep3_results.json')

if __name__ == '__main__':
    main()
