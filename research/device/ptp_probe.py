#!/usr/bin/env python3
"""PTP/MTP extension reverse-engineering probe for the Sony DSC W830.

The W830 grants exactly ONE clean MTP session per USB plug, then wedges
(never send CloseSession). So everything below runs in a SINGLE session.

Hardening:
- Every probe is wrapped in a watchdog thread with a timeout; a hung op
  (device blocks forever on some unsupported opcodes) is recorded as a
  timeout instead of hanging the whole run.
- Results are written to JSON after EVERY probe, so a later hang loses
  nothing captured before it.
"""
import sys, json, threading, queue, traceback
from pmca.commands import usb as cu
from pmca.usb import MtpDevice

# driver selection: 'native' (WPD, wedges) or 'libusb' (WinUSB-bound, owns session)
DRIVER = 'libusb' if '-d' in sys.argv and 'libusb' in sys.argv else 'native'
if '-d' in sys.argv:
    i = sys.argv.index('-d')
    if i + 1 < len(sys.argv):
        DRIVER = sys.argv[i + 1]

PTP = {
    'GetDeviceInfo':      0x1001,
    'OpenSession':        0x1002,
    'GetStorageIDs':      0x1004,
    'GetStorageInfo':     0x1005,
    'GetNumObjects':      0x1006,
    'GetObjectHandles':   0x1007,
    'GetObjectInfo':      0x1008,
    'GetDevicePropDesc':  0x1014,
    'GetDevicePropValue': 0x1015,
    'GetDevicePropList':  0x101b,
}

RESULTS = {'device': 'Sony DSC W830 (VID 054c PID 094b)', 'probes': {}}
JSON_PATH = 'C:/Users/Minhsnguhoa/pmca-re/ptp_probe_results.json'

def save():
    with open(JSON_PATH, 'w') as f:
        json.dump(RESULTS, f, indent=2)

def guarded(fn, timeout=4):
    """Run fn() in a watchdog; return its result or a timeout marker."""
    q = queue.Queue()
    def runner():
        try:
            q.put(('ok', fn()))
        except Exception as e:
            q.put(('exc', repr(e)))
    t = threading.Thread(target=runner, daemon=True)
    t.start(); t.join(timeout)
    if not q.empty():
        kind, val = q.get()
        return val if kind == 'ok' else {'error': val}
    return {'timeout': True, 'note': 'device blocked %ds, no response' % timeout}

def probe_op(drv, code, args, read=False):
    def _do():
        if read:
            rc, data = drv.sendReadCommand(code, args)
            return {'rc': rc, 'rc_hex': hex(rc), 'len': len(data),
                    'hex': data.hex() if len(data) <= 256 else data[:256].hex() + '...'}
        rc = drv.sendCommand(code, args)
        return {'rc': rc, 'rc_hex': hex(rc)}
    return guarded(_do, timeout=4)

def main():
    global RESULTS
    with cu.importDriver('native') as driver:
        found = list(driver.listDevices(cu.SONY_ID_VENDOR))
        if not found:
            print('No Sony device found.'); return
        dev, typ, drv = found[0]
        cam = MtpDevice(drv)   # ONE session, never closed
        try:
            # 1) capture raw DeviceInfo
            r, di = cam.driver.sendReadCommand(PTP['GetDeviceInfo'], [])
            RESULTS['deviceinfo'] = {'rc': hex(r), 'len': len(di)}
            if len(di):
                with open('C:/Users/Minhsnguhoa/pmca-re/di_dump.bin', 'wb') as f:
                    f.write(di)
                RESULTS['deviceinfo']['saved'] = 'di_dump.bin'
            RESULTS['probes']['get_device_info'] = {'rc': hex(r), 'len': len(di)}
            save()

            # 2) vendor opcodes seen in DeviceInfo: 0x9801 0x9802 0x9803 0x9805
            vendor_ops = [0x9801, 0x9802, 0x9803, 0x9805]
            RESULTS['probes']['vendor_ops'] = {}
            for op in vendor_ops:
                key = 'op_0x%04x' % op
                RESULTS['probes']['vendor_ops'][key] = {
                    'sendCommand_noargs': probe_op(cam.driver, op, []),
                    'sendRead_noargs':    probe_op(cam.driver, op, [], read=True),
                    'sendCommand_arg1':   probe_op(cam.driver, op, [1]),
                    'sendRead_arg1':      probe_op(cam.driver, op, [1], read=True),
                }
                save()

            # 3) device property sweep
            prop_codes = [
                0x5001, 0x5002, 0x5003, 0x5004, 0x5005, 0x5007, 0x5008, 0x5009,
                0x500a, 0x500b, 0x500c, 0x500d, 0x500e, 0x500f, 0x5010, 0x5011,
                0x5012, 0xd001, 0xd002, 0xd003, 0xd004, 0xd005,
                0xd100, 0xd101, 0xd102, 0xd103, 0xd104, 0xd105, 0xd106, 0xd10b,
                0xd11e, 0xd11f, 0xd120, 0xd1a2, 0xd1a3, 0xd1a6, 0xd1a7, 0xd1b2,
                0xd1b3, 0xd1c1, 0xd1c2, 0xd1c3, 0xd1c4, 0xd1ca, 0xd1cb, 0xd1cc,
                0xd1cd, 0xd1ce, 0xd1cf, 0xd1d0, 0xd1d1, 0xd1d2, 0xd1d3, 0xd200,
                0xd201, 0xd202, 0xd203, 0xd204, 0xd205, 0xd206, 0xd207, 0xd208,
            ]
            RESULTS['probes']['device_props'] = {}
            for pc in prop_codes:
                desc = probe_op(cam.driver, PTP['GetDevicePropDesc'], [pc], read=True)
                val  = probe_op(cam.driver, PTP['GetDevicePropValue'], [pc], read=True)
                rc = desc.get('rc', 0)
                if (rc == 0x2001) or (desc.get('len', 0) > 0 and 'error' not in desc and not desc.get('timeout')):
                    RESULTS['probes']['device_props']['0x%04x' % pc] = {
                        'desc': desc, 'value': val}
                save()  # incremental - a later hang loses nothing

            # 4) GetDevicePropList
            RESULTS['probes']['get_device_prop_list'] = probe_op(
                cam.driver, PTP['GetDevicePropList'], [], read=True)
            save()

            # 5) session-alive re-check
            r2, sd = cam.driver.sendReadCommand(PTP['GetStorageIDs'], [])
            RESULTS['probes']['storage_check'] = {'rc': hex(r2), 'len': len(sd)}
            save()
        except Exception as e:
            RESULTS['fatal'] = traceback.format_exc()
            save()
    print('Probe complete. Results -> ptp_probe_results.json')
    print('Raw DeviceInfo -> di_dump.bin (%d bytes)' % RESULTS.get('deviceinfo', {}).get('len', 0))

if __name__ == '__main__':
    main()
