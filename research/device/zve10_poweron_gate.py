
"""Gate: wait for the user to power the ZV-E10 back on, then verify pmca sees it as MSC."""
import sys, time, usb.core
from nag_reboot import show_nag

show_nag(title="POWER ON THE ZV-E10",
    msg=("Ready to kick the ZV-E10 into SERVICE MODE.\n\n"
         "1. Power the camera ON (charged is fine).\n"
         "2. USB Connection must be 'Mass Storage' (that's how it was) --\n"
         "   serviceshell needs MSC, not PTP.\n"
         "3. Plug the USB cable in.\n\n"
         "Then click OK."))

from pmca.usb.driver.generic.libusb import _getBackend, _listDevices
print("waiting for camera...", flush=True)
deadline = time.time() + 40
while time.time() < deadline:
    b = _getBackend()
    msc = list(_listDevices(0x054c, 8))
    if msc:
        print("backend=%s  MSC devices: %s" % (b, msc))
        for d in msc:
            print("  PID 0x%04x" % d.idProduct)
        sys.exit(0)
    time.sleep(1)
print("no Sony MSC device appeared after 40s")
sys.exit(1)
