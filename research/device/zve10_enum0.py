
import usb.core, usb.util, usb.backend.libusb0 as lu0
b = lu0.get_backend()
print("libusb0 backend:", b)
devs = list(usb.core.find(find_all=True, backend=b, idVendor=0x054c))
print("sony devices:", len(devs))
for d in devs:
    print("VID %04x PID %04x devclass=%02x" % (d.idVendor, d.idProduct, d.bDeviceClass))
    for s in ("manufacturer","product","serial_number"):
        try: print("   %s=%r" % (s, getattr(d, s)))
        except Exception as e: print("   %s err %s" % (s, e))
    for cfg in d:
        for itf in cfg:
            print("  itf %d class=%02x sub=%02x proto=%02x" % (itf.bInterfaceNumber, itf.bInterfaceClass, itf.bInterfaceSubClass, itf.bInterfaceProtocol))
            for ep in itf:
                print("    ep 0x%02x attr=%02x mps=%d" % (ep.bEndpointAddress, ep.bmAttributes, ep.wMaxPacketSize))
