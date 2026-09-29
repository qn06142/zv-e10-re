#!/usr/bin/env python3
"""Focused 2nd-pass PTP probe for the Sony DSC W830.

Runs in ONE MTP session (device wedges after CloseSession / after 0x9805
sendCommand). Use this right after a fresh USB plug. Captures:
  1. GetDevicePropList (0x101b) FIRST - before any wedging op
  2. 0x9805 sendReadCommand with args 0..31 (the promising uint32 getter)
  3. 0x9805 with [idx, maxlen] style args
  4. 0x9801 / 0x9803 sendRead with a few args
Everything is watchdog-timeboxed so a hang can't kill the run; results
written incrementally to ptp_probe2_results.json.
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

JSON_PATH = 'C:/Users/Minhsnguhoa/pmca-re/ptp_probe2_results.json'
RES = {'device': 'Sony DSC W830', 'probes': {}}

def save():
    with open(JSON_PATH, 'w') as f:
        json.dump(RES, f, indent=2)

def guarded(fn, timeout=4):
    q = queue.Queue()
    def runner():
        try: q.put(('ok', fn()))
        except Exception as e: q.put(('exc', repr(e)))
    t = threading.Thread(target=runner, daemon=True); t.start(); t.join(timeout)
    if not q.empty():
        k, v = q.get(); return v if k == 'ok' else {'error': v}
    return {'timeout': True}

def rd(drv, code, args):
    def _do():
        rc, data = drv.sendReadCommand(code, args)
        return {'rc': rc, 'rc_hex': hex(rc), 'len': len(data),
                'hex': data.hex() if len(data) <= 128 else data[:128].hex() + '...'}
    return guarded(_do, 4)

def main():
    with cu.importDriver(DRIVER) as driver:
        found = list(driver.listDevices(cu.SONY_ID_VENDOR))
        if not found:
            print('No Sony device found.'); return
        dev, typ, drv = found[0]
        cam = MtpDevice(drv)
        try:
            # 1) GetDevicePropList first (0x101b)
            RES['probes']['get_device_prop_list'] = rd(cam.driver, 0x101b, [])
            save()

            # 2) 0x9805 sweep: args 0..31 as sendReadCommand
            RES['probes']['op_9805_read_sweep'] = {}
            for a in range(0, 32):
                RES['probes']['op_9805_read_sweep']['arg_%d' % a] = rd(cam.driver, 0x9805, [a])
            save()

            # 3) 0x9805 with [idx, maxlen] guesses (some cameras take a length)
            RES['probes']['op_9805_len_guess'] = {}
            for a in (1, 2, 4, 8, 16, 0x100, 0x200):
                RES['probes']['op_9805_len_guess']['args_%d' % a] = rd(cam.driver, 0x9805, [1, a])
            save()

            # 4) 0x9801 / 0x9803 as read with a few args
            RES['probes']['op_9801_read'] = {str(a): rd(cam.driver, 0x9801, [a]) for a in (0,1,2)}
            RES['probes']['op_9803_read'] = {str(a): rd(cam.driver, 0x9803, [a]) for a in (0,1,2)}
            save()

            # 5) re-read 0x9805 arg0/arg1 to confirm stable
            RES['probes']['op_9805_recheck'] = {
                'arg0': rd(cam.driver, 0x9805, []),
                'arg1': rd(cam.driver, 0x9805, [1]),
            }
            save()
        except Exception as e:
            RES['fatal'] = traceback.format_exc(); save()
    print('Pass 2 probe complete -> ptp_probe2_results.json')

if __name__ == '__main__':
    main()
