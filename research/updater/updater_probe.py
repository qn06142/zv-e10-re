import usb.backend.libusb1 as lb
import usb.core, usb.util, struct, glob, sys, time, threading

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]

DLL = glob.glob((ROOT_REPO / '.venv/Lib/site-packages/libusb/_platform/windows/x86_64/libusb-1.0.dll').as_posix())[0]
be = lb.get_backend(find_library=lambda x: DLL)

VID, PID_UPDATER = 0x054c, 0x0994
OUT_LOG = (ROOT_REPO / 'updater_probe_log.txt').as_posix()

def log(*a):
    line = " ".join(str(x) for x in a)
    with open(OUT_LOG, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)

def cbw(opcode, cdb, xfer, in_dir):
    cdb = (bytes([opcode]) + cdb[1:]).ljust(16, b"\x00")[:16]
    flag = 0x80 if in_dir else 0x00
    return b"USBC" + struct.pack("<IIB", 0x1234, xfer, flag) + bytes([len(cdb) & 0x1f]) + cdb

def exec_cmd(dev, opcode, cdb, xfer=256, in_dir=True, timeout=2000):
    OUT, IN = 0x02, 0x81
    try:
        dev.write(OUT, cbw(opcode, cdb, xfer, in_dir), timeout=timeout)
    except usb.core.USBError as e:
        return None, None, "WRITE: "+str(e)[:80]
    data = b""
    if in_dir and xfer:
        try:
            data = bytes(dev.read(IN, xfer, timeout=timeout))
        except usb.core.USBError as e:
            return None, None, "READ: "+str(e)[:80]
    try:
        csw = bytes(dev.read(IN, 13, timeout=timeout))
    except usb.core.USBError as e:
        return data, None, "CSW: "+str(e)[:80]
    status = csw[12] if len(csw) >= 13 else None
    return data, status, None

def probe(dev):
    # report which driver Windows bound to this 0x0994 instance
    try:
        import subprocess
        out = subprocess.run(
            ["powershell","-c",
             "Get-PnpDevice -PresentOnly | Where-Object {$_.InstanceId -like '*VID_054C*PID_0994*'} | Select-Object InstanceId,Service | Format-List | Out-String"],
            capture_output=True, text=True, timeout=8000).stdout
        log("driver binding for 0x0994:", (out.strip() or "(none)")[:200])
    except Exception as e:
        log("driver query err:", str(e)[:60])
    try:
        dev.set_configuration()
        usb.util.claim_interface(dev, 0)
    except usb.core.USBError as e:
        log("CLAIM FAILED:", str(e)[:80]); return
    log("CLAIMED updater device, config set, iface0 claimed")
    # standard
    for name, op, cdb, xf in [("INQUIRY",0x12,bytes([0x12,0,0,0,0x24,0]),36),
                              ("READ_CAPACITY",0x25,bytes([0x25,0,0,0,0,0,0,0,0,0]),8),
                              ("GET_MAX_LUN",0xFE,bytes([0xFE,0,0,0,0,0,0,0,0,0]),1)]:
        d,st,err = exec_cmd(dev, op, cdb, xf)
        log("  %s: status=%s err=%s data=%s" % (name, st, err, (d[:32].hex() if d else "")))
    # vendor opcode sweep (read-style, IN, 512 alloc)
    hits = []
    for op in list(range(0xC0,0x100)) + [0x7a,0x7b,0xa0,0xa1]:
        cdb = bytes([op,0,0,0,0,0,0,0,0x02,0x00])
        d,st,err = exec_cmd(dev, op, cdb, 512, timeout=1500)
        if d is not None and len(d) > 0 and any(b!=0 for b in d[:32]):
            tag = " <-- DATA" if st==0 else ""
            log("  vendor op=0x%02x status=%s len=%d%s hex=%s" % (op, st, len(d), tag, d[:24].hex()))
            if st==0:
                hits.append((op, d))
                open((ROOT_REPO / 'vendor_0x%02x.bin').as_posix() % op, "wb").write(d)
    log("VENDOR HITS (status0, returned data):", [hex(o) for o,_ in hits])
    usb.util.release_interface(dev, 0)

def watch(seconds=300):
    log("=== updater-mode watcher armed (PID 0x0994), polling %ds ===" % seconds)
    deadline = time.time() + seconds
    while time.time() < deadline:
        dev = usb.core.find(idVendor=VID, idProduct=PID_UPDATER, backend=be)
        if dev is not None:
            log(">>> UPDATER DEVICE DETECTED (0x0994) at t=%.1fs" % (deadline-time.time()))
            try:
                probe(dev)
            except Exception as e:
                log("probe exception:", e)
            return
        time.sleep(0.2)
    log("watch expired: 0x0994 never appeared in %ds" % seconds)

if __name__ == "__main__":
    watch()
