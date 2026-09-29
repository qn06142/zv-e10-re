
"""Gate: nag user to switch ZV-E10 to PTP mode + replug, then wait for the PTP PID."""
import sys, time, usb.core, usb.backend.libusb0 as lu0
from nag_reboot import show_nag

show_nag(title="ZV-E10 -> PTP MODE",
    msg=("The ZV-E10 is enumerating as USB Mass Storage (PID 0x0D95).\\n"
         "pmca needs PTP/MTP.\\n\\n"
         "On the camera:  MENU > Setup > USB > USB Connection\\n"
         "   set it to  'PC Remote'  (or 'MTP')  -- NOT 'Mass Storage'.\\n"
         "Also make sure a memory card is inserted.\\n\\n"
         "Then unplug + replug the USB cable and click OK."))

b = lu0.get_backend()
print("waiting for Sony device to re-enumerate...")
deadline = time.time() + 30
seen = None
while time.time() < deadline:
    devs = list(usb.core.find(find_all=True, backend=b, idVendor=0x054c)) or \
           list(usb.core.find(find_all=True, idVendor=0x054c))
    for d in devs:
        try: itf = d.get_active_configuration()[(0,0)]
        except Exception: continue
        info = (d.idProduct, itf.bInterfaceClass, itf.bInterfaceSubClass, itf.bInterfaceProtocol)
        if info != seen:
            seen = info
            print("  PID 0x%04x  itf class=%02x sub=%02x proto=%02x" % info, flush=True)
        if (itf.bInterfaceClass, itf.bInterfaceSubClass, itf.bInterfaceProtocol) == (6,1,1):
            print("PTP/StillImage interface detected on PID 0x%04x -- ready" % d.idProduct)
            sys.exit(0)
    time.sleep(1)
print("no PTP interface appeared; last seen:", seen)
sys.exit(1)
