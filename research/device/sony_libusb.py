import usb.core, usb.util, struct, time

VEND=0x054c; PROD=0x0d95
dev = usb.core.find(idVendor=VEND, idProduct=PROD)
assert dev, "camera not found"
print("found cam bus=%d addr=%d" % (dev.bus, dev.address))
try: dev.reset(); time.sleep(1)
except Exception as e: print("reset note", e)

cfg = dev.get_active_configuration()
intf = cfg[(0,0)]
ep_out = usb.util.find_descriptor(intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)==usb.util.ENDPOINT_OUT)
ep_in  = usb.util.find_descriptor(intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)==usb.util.ENDPOINT_IN)
print("ep_out=0x%02x ep_in=0x%02x" % (ep_out.bEndpointAddress, ep_in.bEndpointAddress))
try:
    dev.clear_halt(ep_out); dev.clear_halt(ep_in)
except Exception as e: print("clearhalt note", e)

was_attached=False
try:
    if dev.is_kernel_driver_active(0):
        dev.detach_kernel_driver(0); was_attached=True
except Exception as e: print("detach note:", e)
usb.util.claim_interface(dev, 0)

TAG=[0x11223344]
def send_cbw(cdb, flags, xfer):
    header = b"USBC" + struct.pack("<II", TAG[0], xfer) + struct.pack("<BBB", flags, 0, len(cdb))
    cbw = header + cdb.ljust(16, b"\x00")
    assert len(cbw)==31, len(cbw)
    dev.write(ep_out, cbw, 5000)
    TAG[0]+=1

def inquiry():
    cdb = bytes([0x12,0,0,0,36,0])
    send_cbw(cdb, 0x80, 36)
    data = dev.read(ep_in, 36, 5000)
    csw = dev.read(ep_in, 13, 5000)
    return bytes(data), bytes(csw)

d, csw = inquiry()
print("INQUIRY:", d[:40].hex(), "ven=", d[8:16].split(b'\x00')[0], "prod=", d[16:32].split(b'\x00')[0])
print("CSW:", csw.hex(), "status=", csw[12] if len(csw)==13 else "?")

def cam_cmd_struct(code, payload_len=0x30, extra=b""):
    s = bytearray(68)
    struct.pack_into("<H", s, 4, 0x2c)
    s[0x0b]=code
    struct.pack_into("<I", s, 0x1c, payload_len)
    s[0x20:0x20+len(extra)]=extra
    return bytes(s)

# Probe candidate opcodes as DATA-OUT (host->cam) with the 68-byte struct as payload.
# Build CDB[0]=op, and try the disasm-derived CDB tail 0x44/0x0d bytes too.
OPS = [0x0d,0x44,0x12,0xC9,0xE9,0xEA,0xEC,0xED,0xEF]
for op in OPS:
    s68 = cam_cmd_struct(0x12)
    cdb = bytearray(16)
    cdb[0]=op
    # disasm call #1 CDB bytes: Cdb[4..7]=0d 44 00 00, Cdb[8..11]=60 08 00 00
    cdb[4]=0x0d; cdb[5]=0x44; cdb[8]=0x60; cdb[9]=0x08
    try:
        send_cbw(bytes(cdb), 0x00, len(s68))   # DATA-OUT
        dev.write(ep_out, s68, 3000)
        # read CSW (no data phase on OUT)
        csw = dev.read(ep_in, 13, 3000)
        print("op=%#04x OUT -> csw=%s status=%s" % (op, bytes(csw).hex(),
              bytes(csw)[12] if len(csw)==13 else "?"))
    except Exception as e:
        print("op=%#04x OUT err %s" % (op, str(e)[:40]))
    # also try DATA-IN variant
    try:
        send_cbw(bytes(cdb), 0x80, len(s68))
        dev.write(ep_out, s68, 3000)
        resp = dev.read(ep_in, len(s68), 3000)
        csw = dev.read(ep_in, 13, 3000)
        print("op=%#04x IN  -> resp=%s csw=%s" % (op, bytes(resp).hex()[:32],
              bytes(csw)[12] if len(csw)==13 else "?"))
    except Exception as e:
        print("op=%#04x IN err %s" % (op, str(e)[:40]))
    try: dev.reset(); time.sleep(0.5)
    except: pass

usb.util.release_interface(dev, 0)
if was_attached:
    try: dev.attach_kernel_driver(0)
    except: pass
