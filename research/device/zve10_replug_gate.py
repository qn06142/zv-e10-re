
"""Gate: replug ZV-E10; enumerate EVERY Sony PID + interface class (service mode spawns a new PID)."""
import sys, time, usb.core

def scan():
    out = []
    backs = [None]
    try:
        import usb.backend.libusb0 as l0; backs.append(l0.get_backend())
    except Exception: pass
    seen = set()
    for b in backs:
        try: devs = list(usb.core.find(find_all=True, backend=b, idVendor=0x054c))
        except Exception: continue
        for d in devs:
            key = (d.idProduct, d.bus, d.address)
            if key in seen: continue
            seen.add(key)
            info = {"pid": d.idProduct, "backend": "libusb0" if b else "libusb1", "itfs": []}
            try:
                for itf in d.get_active_configuration():
                    info["itfs"].append((itf.bInterfaceClass, itf.bInterfaceSubClass, itf.bInterfaceProtocol))
            except Exception as e:
                info["itfs"] = "err:%s" % e
            try: info["product"] = d.product
            except Exception: info["product"] = "?"
            out.append(info)
    return out

if "--scan" not in sys.argv:
    from nag_reboot import show_nag
    show_nag(title="REPLUG THE ZV-E10",
        msg=("Service mode WORKED (auth passed, shell opened) but that\n"
             "session was consumed and the camera left the bus.\n\n"
             "1. Unplug the USB cable.\n"
             "2. Camera ON, USB Connection = 'Mass Storage'.\n"
             "3. Plug it back in.\n\n"
             "Click OK -- I'll enumerate every PID it presents."))

print("scanning for any Sony device...", flush=True)
deadline = time.time() + 40
last = None
while time.time() < deadline:
    r = scan()
    if r:
        for i in r:
            print("  PID 0x%04x [%s] product=%r itfs=%s" % (i["pid"], i["backend"], i["product"], i["itfs"]))
        sys.exit(0)
    time.sleep(1)
print("no Sony device after 40s")
sys.exit(1)
