
from pmca.commands import usb as cu
for drvname in ("native",):
    with cu.importDriver(drvname) as driver:
        found = list(driver.listDevices(cu.SONY_ID_VENDOR))
        print(drvname, "found", len(found))
        for f in found:
            print("  ", f)
