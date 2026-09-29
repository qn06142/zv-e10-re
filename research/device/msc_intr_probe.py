#!/usr/bin/env python3
"""
msc_intr_probe.py - probe the MSC interrupt IN endpoint (0x83) of the Sony DSC
W830 (VID_054C/PID_08B3, WinUSB-bound). The bulk endpoints (0x81/0x02) gave
standard MSC + STALL on vendor CDBs; the interrupt endpoint is unused and may
carry vendor/service control messages. We read it (with timeout) and capture
any data. Non-destructive.

Run via run_after_reboot.py (needs a fresh plug; may wedge the handle).
"""
import sys, json, usb.core, usb.util

VID, PID = 0x054c, 0x08b3
TIMEOUT = 2000
JSON_PATH = 'C:/Users/Minhsnguhoa/pmca-re/msc_intr_results.json'
RES = {'reads': []}

def eprint(*a):
    print(*a); sys.stdout.flush()

def main():
    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        eprint('No Sony MSC device'); return
    eprint('Found VID_054C PID_08B3')
    try:
        try:
            dev.set_configuration()
        except NotImplementedError:
            pass
        cfg = dev.get_active_configuration()
        intf = cfg[(0, 0)]
        INTR = None
        for ep in intf:
            if (usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN
                    and (ep.bmAttributes & 0x03) == usb.util.ENDPOINT_TYPE_INTR):
                INTR = ep.bEndpointAddress
        if INTR is None:
            eprint('No interrupt IN endpoint found')
            RES['error'] = 'no interrupt endpoint'
            return
        eprint('Interrupt IN ep=0x%02X' % INTR)
        try:
            usb.util.claim_interface(dev, 0)
            eprint('claimed iface 0')
        except Exception as e:
            eprint('claims note: %r' % e)
        # read a few times (interrupt may be polled by camera to push events)
        for i in range(10):
            try:
                buf = dev.read(INTR, 64, TIMEOUT)
                data = bytes(buf)
                RES['reads'].append({'n': i, 'len': len(data), 'data_hex': data.hex()})
                eprint('  read %d: %d bytes %s' % (i, len(data), data.hex()))
            except usb.core.USBError as e:
                msg = str(e)
                RES['reads'].append({'n': i, 'error': msg})
                eprint('  read %d: %s' % (i, msg))
                if 'timed out' in msg.lower() or 'timeout' in msg.lower():
                    # interrupt often just has no data -> stop early
                    break
    except Exception as e:
        import traceback
        RES['fatal'] = traceback.format_exc()
    finally:
        try: usb.util.dispose_resources(dev)
        except Exception: pass
        with open(JSON_PATH, 'w') as f:
            json.dump(RES, f, indent=2)
    eprint('MSC interrupt probe -> %s' % JSON_PATH)

if __name__ == '__main__':
    main()
