#!/usr/bin/env python3
"""Minimal Sony DSC W830 (PTP/MTP) RE probe built on pmca's WPD driver.

Usage:
    .venv/Scripts/activate
    python re_probe.py            # device info + storage + root handles
    python re_probe.py info       # GetDeviceInfo only
    python re_probe.py tree       # descend one level under storage root

IMPORTANT device quirk (learned the hard way):
The W830's MTP/WPD stack WEDGES (returns COM 0x-7ff8f9a3 and stalls) if you
ever send it a CloseSession, or if you open/close sessions repeatedly. Once
wedged it only recovers on a physical USB re-plug. So this script opens exactly
ONE session (via pmca's MtpDevice ctor, which accepts the "already open" rc) and
never closes it. Re-running just reuses the live session.
"""
import sys
from pmca.commands import usb as cu
from pmca.usb import MtpDevice

PTP_OC_GetStorageIDs    = 0x1004
PTP_OC_GetNumObjects    = 0x1006
PTP_OC_GetObjectHandles = 0x1007
PTP_OC_GetObjectInfo    = 0x1008
PTP_RC_OK               = 0x2001

def obj_info(driver, handle):
    """Parse a PTP ObjectInfo response (PTP spec layout)."""
    r, data = driver.sendReadCommand(PTP_OC_GetObjectInfo, [handle])
    if r != PTP_RC_OK or len(data) < 30:
        return None
    storage = int.from_bytes(data[0:4], 'little')
    fmt     = int.from_bytes(data[4:6], 'little')
    off = 30  # PTP ObjectInfo fixed header precedes the filename
    if off >= len(data):
        return dict(storage=storage, fmt=fmt, name='')
    nlen = data[off]; off += 1
    name = data[off:off + 2 * nlen].decode('utf-16-le', 'replace').rstrip('\x00')
    return dict(storage=storage, fmt=fmt, name=name)

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'root'
    with cu.importDriver('native') as driver:
        found = list(driver.listDevices(cu.SONY_ID_VENDOR))
        if not found:
            print('No Sony device found.'); return
        dev, typ, drv = found[0]
        cam = MtpDevice(drv)   # opens exactly ONE session; never closed
        try:
            if mode == 'info':
                info = cam.getDeviceInfo()
                print('=== DeviceInfo ===')
                print('  manufacturer :', info.manufacturer)
                print('  model        :', info.model)
                print('  serial       :', info.serialNumber)
                print('  vendor_ext   :', repr(info.vendorExtension))
                print('  operations   :', [hex(o) for o in sorted(info.operationsSupported)])
                return

            # storage root
            r, data = cam.driver.sendReadCommand(PTP_OC_GetStorageIDs, [])
            storage = int.from_bytes(data[4:8], 'little')
            print('storage id = 0x%08x (resp %s)' % (storage, hex(r)))
            r, data = cam.driver.sendReadCommand(PTP_OC_GetNumObjects, [storage, 0, 0xffffffff])
            total = int.from_bytes(data[:4], 'little') if len(data) >= 4 else -1
            print('total objects :', total)
            r, data = cam.driver.sendReadCommand(PTP_OC_GetObjectHandles, [storage, 0, 0xffffffff])
            n = int.from_bytes(data[:4], 'little') if len(data) >= 4 else 0
            if n > 0:
                print('root handles  :', [hex(int.from_bytes(data[4 + i * 4:8 + i * 4], 'little')) for i in range(n)])
                if mode == 'tree':
                    for i in range(n):
                        h = int.from_bytes(data[4 + i * 4:8 + i * 4], 'little')
                        info = obj_info(cam.driver, h)
                        if info:
                            print('  0x%08x fmt=0x%04x %r' % (h, info['fmt'], info['name']))
                        else:
                            print('  0x%08x (info err)' % h)
            else:
                # The W830's minimal MTP stack reports zero enumerable objects
                # (GetNumObjects=0, GetObjectHandles=0) even though it has a
                # storage volume. Its filesystem isn't exposed via standard PTP
                # object enumeration - this is a device limitation, not a bug.
                print('root handles  : (none - W830 MTP stack does not expose objects)')
        finally:
            # Do NOT send CloseSession - it wedges the W830. The WPD handle is
            # released when the process exits; the session simply stays open.
            pass

if __name__ == '__main__':
    main()
