"""lens_query.py -- read E-mount lens identity over the USB bus (read-only).

Reuses the raw USB tunnel from sony_cmd.py:
  - find Sony MSC device (VID 0x054c, PID 0x0d95)
  - claim interface, build 68-byte "cam_struct" (cmd code @ off 0x0b)
  - send via USBC CBW, read response

Goal: enter lens updater mode (PID flips to 0x994) and query the lens via CAIF
GetLensVersion, returning lens FW version / lens_id / serial. READ-ONLY -- no flash.

The exact host->camera USB command code that maps to GetLensVersion is NOT known
statically (see LENS_PROTOCOL.md). So this script:
  1) scans struct codes 0x00..0xFF for one that flips PID to 0x994 (updater entry),
  2) once in updater mode, tries a set of candidate GetLensVersion query codes and
     dumps the raw lens responses so we can identify which one returns lens data.

Camera must be ON and connected via USB (MSC mode, PID 0x0d95). Run from pmca-re venv:
  .venv/Scripts/python.exe lens_query.py

NOTE: untested -- camera currently OFF BUS. Built from static RE only.
"""
import usb.core, usb.util, struct, time, sys

VEND = 0x054c
MSC_PID = 0x0d95
UPD_PID = 0x0994
TAG = [0x11223344]

def find_dev(pid):
    return usb.core.find(idVendor=VEND, idProduct=pid)

def claim(dev):
    try: dev.reset(); time.sleep(1)
    except: pass
    cfg = dev.get_active_configuration(); intf = cfg[(0, 0)]
    eo = usb.util.find_descriptor(intf, custom_match=lambda e:
        usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
    ei = usb.util.find_descriptor(intf, custom_match=lambda e:
        usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
    try: dev.clear_halt(eo); dev.clear_halt(ei)
    except: pass
    was = False
    try:
        if dev.is_kernel_driver_active(0): dev.detach_kernel_driver(0); was = True
    except: pass
    usb.util.claim_interface(dev, 0)
    return eo, ei, was

def send_cbw(dev, ep_out, cdb, flags, xfer):
    h = b"USBC" + struct.pack("<II", TAG[0], xfer) + struct.pack("<BBB", flags, 0, len(cdb))
    cbw = h + cdb.ljust(16, b"\x00")
    assert len(cbw) == 31
    dev.write(ep_out, cbw, 3000); TAG[0] += 1

def cam_struct(code, pl=0x30, extra=b""):
    s = bytearray(68)
    struct.pack_into("<H", s, 4, 0x2c)
    s[0x0b] = code
    struct.pack_into("<I", s, 0x1c, pl)
    s[0x20:0x20+len(extra)] = extra
    return bytes(s)

def pid_now():
    d = find_dev(UPD_PID)
    return UPD_PID if d else None

def main():
    dev = find_dev(MSC_PID)
    if not dev:
        print("camera (0x0d95) not found -- is it on USB in MSC mode?")
        sys.exit(1)
    ep_out, ep_in, was = claim(dev)

    # 1) scan struct codes for updater-mode entry (PID -> 0x994)
    print("--- scanning struct codes 0x00..0xFF for updater entry (PID 0x994) ---")
    updater_code = None
    for code in range(0x100):
        s68 = cam_struct(code)
        try:
            send_cbw(dev, ep_out, bytes([0x7a,0,0,0,0x0d,0x44,0,0,0x60,0x08,0,0,0,0,0,0]), 0x00, len(s68))
            dev.write(ep_out, s68, 2000)
            csw = dev.read(ep_in, 13, 2000)
            time.sleep(0.3)
            if pid_now() == UPD_PID:
                updater_code = code
                print("*** UPDATER MODE via code=%#04x" % code)
                break
        except Exception:
            pass
        try: dev.reset(); time.sleep(0.1)
        except: pass
        if code % 32 == 0:
            print("  scanned %#04x pid=%s" % (code, hex(pid_now()) if pid_now() else "0x0d95"))
    if updater_code is None:
        print("no updater entry found in 0x00..0xFF -- cannot reach lens CAIF from host")
        usb.util.release_interface(dev, 0)
        return

    # 2) in updater mode: try candidate GetLensVersion query codes, dump responses
    print("\n--- querying lens (GetLensVersion candidates) ---")
    cand = [0x12, 0x20, 0x21, 0x30, 0x31, 0x40, 0x41, 0x50, 0x51, 0x60, 0x61, 0x70, 0x71]
    for code in cand:
        s68 = cam_struct(code)
        try:
            send_cbw(dev, ep_out, bytes([0x7a,0,0,0,0x0d,0x44,0,0,0x60,0x08,0,0,0,0,0,0]), 0x80, 68)
            dev.write(ep_out, s68, 2000)
            resp = dev.read(ep_in, 68, 2000)
            print("code=%#04x -> %s" % (code, bytes(resp).hex()))
        except Exception as e:
            print("code=%#04x err %s" % (code, str(e)[:40]))
        time.sleep(0.2)

    usb.util.release_interface(dev, 0)
    if was:
        try: dev.attach_kernel_driver(0)
        except: pass

if __name__ == "__main__":
    main()
