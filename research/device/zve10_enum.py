
import usb.core, usb.util
for d in usb.core.find(find_all=True, idVendor=0x054c):
    print("VID %04x PID %04x class=%s" % (d.idVendor, d.idProduct, d.bDeviceClass))
    try: print("  mfg=%r prod=%r ser=%r" % (d.manufacturer, d.product, d.serial_number))
    except Exception as e: print("  strings unavailable:", e)
    for cfg in d:
        for itf in cfg:
            print("  itf %d alt %d class=%02x sub=%02x proto=%02x" % (
                itf.bInterfaceNumber, itf.bAlternateSetting,
                itf.bInterfaceClass, itf.bInterfaceSubClass, itf.bInterfaceProtocol))
            for ep in itf:
                print("    ep 0x%02x attr=%02x mps=%d" % (ep.bEndpointAddress, ep.bmAttributes, ep.wMaxPacketSize))
