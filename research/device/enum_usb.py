import usb.core, usb.util
devs = usb.core.find(find_all=True)
sony=[]
for d in devs:
    try:
        vid=d.idVendor; pid=d.idProduct
    except Exception:
        continue
    if vid!=0x054c:
        continue
    print("SONY: vid=%#06x pid=%#06x bus=%d addr=%d" % (vid, pid, d.bus, d.address))
    try:
        man = usb.util.get_string(d, 256, d.iManufacturer) or ""
        prod= usb.util.get_string(d, 256, d.iProduct) or ""
        print("  man=%r prod=%r" % (man, prod))
    except Exception as e:
        print("  str err", e)
    try:
        cfg = d.get_active_configuration()
        for intf in cfg:
            eps=[]
            for ep in intf:
                try: eps.append("%s%d"%("IN" if usb.util.endpoint_direction(ep.bEndpointAddress)==usb.util.ENDPOINT_IN else "OUT", ep.bEndpointAddress&0xf))
                except: pass
            print("   intf%d alt%d cls=%#04x sub=%#04x proto=%#04x eps=%s" % (
                intf.bInterfaceNumber, intf.bAlternateSetting,
                intf.bInterfaceClass, intf.bInterfaceSubClass, intf.bInterfaceProtocol, eps))
    except Exception as e:
        print("   cfg/intf err", e)
    sony.append((vid,pid))
print("TOTAL SONY:", len(sony))
