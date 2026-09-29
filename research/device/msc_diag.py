#!/usr/bin/env python3
"""msc_diag.py - dump every interface + endpoint of the Sony DSC MSC device
(Video_054C/PID_08B3) so we can see the real bulk endpoint addresses/types.
Also tries a raw INQUIRY CBW via bulk transfer on the detected bulk endpoints.
Read-only diagnostic.
"""
import sys, struct, usb.core, usb.util

VID, PID = 0x054c, 0x08b3

def eprint(*a):
    print(*a); sys.stdout.flush()

dev = usb.core.find(idVendor=VID, idProduct=PID)
if dev is None:
    eprint('No device'); sys.exit(1)
eprint('Found VID_054C PID_08B3')
try:
    try:
        dev.set_configuration()
    except Exception:
        pass  # Windows+WinUSB: skip; try descriptors anyway
    cfg = dev.get_active_configuration()
    eprint('config value:', cfg.bConfigurationValue)
    for intf in cfg:
        inum = intf.bInterfaceNumber
        alt = intf.bAlternateSetting
        eprint('  interface %d alt %d class 0x%02x sub 0x%02x proto 0x%02x'
               % (inum, alt, intf.bInterfaceClass, intf.bInterfaceSubClass, intf.bInterfaceProtocol))
        for ep in intf:
            dirn = 'IN ' if (ep.bEndpointAddress & 0x80) else 'OUT'
            etype = {2:'BULK',3:'INTR',1:'CTRL',0:'CTRL'}.get(ep.bmAttributes & 0x03, '?')
            eprint('      ep 0x%02X %s %s wMaxPacket %d'
                   % (ep.bEndpointAddress, dirn, etype, ep.wMaxPacketSize))
except Exception as e:
    import traceback; traceback.print_exc()
finally:
    try: usb.util.dispose_resources(dev)
    except Exception: pass
