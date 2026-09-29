#!/usr/bin/env python3
"""Raw PTP/MTP vendor-op packet capture for the Sony DSC W830 (libusb/WinUSB).

pmca's generic MtpDriver assumes every op has a data phase, so vendor ops that
reply with only a response packet throw 'Wrong response type: 0x3'. This script
talks to the camera at the pyusb bulk level: it sends a PTP command block and
then reads BOTH packets the camera sends (data and/or response), dumping each
packet's type/code/transaction and raw bytes. That reveals the true behavior
of the 0x98xx vendor ops.

Single session: opens the interface once, never resets/closes it mid-run
(closeSession wedges the W830). Run once per USB plug.
"""
import sys, json, struct, threading, queue
import usb.core, usb.util

import pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]

VENDOR = 0x054c
PRODUCT = 0x094b
SONY_OPS = [0x9801, 0x9802, 0x9803, 0x9805]
TYPE_CMD, TYPE_DATA, TYPE_RESP = 1, 2, 3
TIMEOUT = 3000

JSON_PATH = (REPO / 'ptp_raw_results.json').as_posix()
RES = {'device': 'Sony DSC W830', 'captures': {}}

def save():
    with open(JSON_PATH, 'w') as f:
        json.dump(RES, f, indent=2)

def find_ep(dev):
    cfg = dev.get_active_configuration()
    intf = cfg[(0, 0)]
    ep_in = ep_out = None
    for ep in intf:
        if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN:
            ep_in = ep.bEndpointAddress
        else:
            ep_out = ep.bEndpointAddress
    return ep_in, ep_out

def send_ptp(dev, ep_in, ep_out, code, args, transaction=1, read_packets=2):
    """Send a PTP command block, then read up to `read_packets` bulk packets
    raw (no type assumption). Returns list of (type, code, raw_payload)."""
    # PTP command header: size(4) type(2)=1 code(2) transaction(4) + 32-bit args
    argbytes = b''.join(struct.pack('<I', a) for a in args)
    hdr = struct.pack('<IHHI', 12 + len(argbytes), TYPE_CMD, code, transaction)
    pkt = hdr + argbytes
    dev.write(ep_out, pkt, TIMEOUT)
    out = []
    for _ in range(read_packets):
        try:
            raw = dev.read(ep_in, 512, TIMEOUT).tobytes()
        except usb.core.USBError as e:
            out.append({'type': None, 'error': 'USBError: %s' % e})
            break
        if len(raw) < 12:
            out.append({'type': None, 'raw': raw.hex()})
            break
        size, ptype, pcode, txn = struct.unpack('<IHHI', raw[:12])
        payload = raw[12:size] if size <= len(raw) else raw[12:]
        out.append({'type': ptype, 'type_name': {1:'CMD',2:'DATA',3:'RESP'}.get(ptype,'?'),
                    'code': pcode, 'code_hex': hex(pcode), 'txn': txn,
                    'payload_hex': payload.hex() if payload else ''})
    return out

def guarded(fn, timeout=5):
    q = queue.Queue()
    def runner():
        try: q.put(('ok', fn()))
        except Exception as e: q.put(('exc', repr(e)))
    t = threading.Thread(target=runner, daemon=True); t.start(); t.join(timeout)
    if not q.empty():
        k, v = q.get(); return v if k == 'ok' else {'error': v}
    return {'timeout': True}

def main():
    dev = usb.core.find(idVendor=VENDOR, idProduct=PRODUCT)
    if dev is None:
        print('No Sony device found (libusb).'); return
    claimed = False
    try:
        # detach any kernel driver, claim interface 0
        try:
            if dev.is_kernel_driver_active(0):
                dev.detach_kernel_driver(0)
        except Exception:
            pass
        usb.util.claim_interface(dev, 0)
        claimed = True
        dev.default_timeout = TIMEOUT
        ep_in, ep_out = find_ep(dev)
        # open a session (PTP OpenSession = 0x1002, session id 1)
        RES['session_open'] = guarded(lambda: send_ptp(dev, ep_in, ep_out, 0x1002, [1], 1, 2))
        save()
        for op in SONY_OPS:
            RES['captures']['op_0x%04x' % op] = {}
            for nargs in (0, 1, 2):
                for argvals in ([], [1], [1, 0x200]):
                    key = 'nargs%d_%s' % (nargs, argvals)
                    RES['captures']['op_0x%04x' % op][key] = guarded(
                        lambda o=op, a=(argvals[:nargs] if nargs else []):
                            send_ptp(dev, ep_in, ep_out, o, a, 1, 2), 5)
                    save()
    finally:
        save()
        if claimed:
            try: usb.util.release_interface(dev, 0)
            except Exception: pass
        try: usb.util.dispose_resources(dev)
        except Exception: pass
    print('Raw capture complete -> ptp_raw_results.json')

if __name__ == '__main__':
    main()
