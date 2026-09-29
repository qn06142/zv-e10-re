#!/usr/bin/env python3
"""
Single-session deep probe for the Sony DSC W830 (libusb). Packs everything
useful into ONE clean MTP session (one replug):

  1) Wake ops with the known cumulative handshake (0x9801,0x9805,0x9803,0x9805).
  2) Try 2-arg forms on awake ops (0x9806/0x9807/0x9808) mimicking
     GetObjectHandles(storage, parent): [0x00020001, 0xFFFFFFFF],
     [0, 0xFFFFFFFF], [parent, count] sweeps -- looking for a handle list.
  3) Try a LONGER handshake (extra 0x9805/0x9801 steps) then rescan
     0x980b..0x981f to see if any further op wakes up.
  4) Try 0x9805 as a potential GetObject(handle): 0x9805([handle]) for a few
     handle-like values.

Captures any DATA > 4 bytes (potential handle list / object). -d libusb.
"""
import sys, json
from pmca.commands import usb as cu
from pmca.usb import MtpDevice
from pmca.usb.driver.generic import MtpDriver

TNAME = {1:'CMD',2:'DATA',3:'RESP'}
JSON_PATH = 'C:/Users/Minhsnguhoa/pmca-re/ptp_deep2_results.json'
RES = {'wake': {}, 'two_arg': {}, 'longer_handshake_rescan': {}, 'op9805_as_getobj': {}}

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
    seq = ((0x9801,[1]),(0x9805,[1]),(0x9803,[1]),(0x9805,[1]))
    out = {}
    for op, a in seq:
        pk = tolerant(drv, op, a)
        out['op_0x%04x' % op] = {'resp': resp_of(pk), 'data': data_of(pk)}
    return out

def scan_range(drv, lo, hi):
    out = {}
    for op in range(lo, hi):
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
            RES['wake'] = wake(cam.driver)

            # 2) 2-arg forms on awake ops (storage, parent) style
            forms = [
                [0x00020001, 0xFFFFFFFF],
                [0,           0xFFFFFFFF],
                [0xFFFFFFFF,  0xFFFFFFFF],
                [0x00020001,  0x00000000],
                [0x00010001,  0xFFFFFFFF],
                [0x00020001,  0x00010001],
            ]
            for op in (0x9806, 0x9807, 0x9808):
                RES['two_arg']['op_0x%04x' % op] = {}
                for f in forms:
                    pk = tolerant(cam.driver, op, f)
                    dhex = data_of(pk)
                    RES['two_arg']['op_0x%04x' % op]['%s' % f] = {
                        'resp': resp_of(pk),
                        'data_len': len(dhex)//2 if dhex else 0,
                        'data': dhex[:64] if dhex else None,
                    }

            # 3) LONGER handshake then rescan 0x980b..0x981f
            for op, a in ((0x9805,[1]),(0x9801,[1]),(0x9803,[1]),(0x9805,[1]),
                          (0x9803,[1]),(0x9805,[1])):
                tolerant(cam.driver, op, a)
            RES['longer_handshake_rescan'] = scan_range(cam.driver, 0x980b, 0x9820)

            # 4) 0x9805 as GetObject(handle)
            for h in (0x00010001, 0x00020001, 0x00030001, 0x10000001):
                pk = tolerant(cam.driver, 0x9805, [h])
                dhex = data_of(pk)
                RES['op9805_as_getobj']['handle_0x%08x' % h] = {
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
    print('Deep2 probe -> ptp_deep2_results.json')

if __name__ == '__main__':
    main()
