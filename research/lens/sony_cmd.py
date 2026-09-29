import usb.core, usb.util, struct, time

VEND=0x054c
dev = usb.core.find(idVendor=VEND, idProduct=0x0d95)
assert dev, "cam (0x0d95) not found"
def claim():
    global dev
    try: dev.reset(); time.sleep(1)
    except: pass
    cfg=dev.get_active_configuration(); intf=cfg[(0,0)]
    eo=usb.util.find_descriptor(intf,custom_match=lambda e:usb.util.endpoint_direction(e.bEndpointAddress)==usb.util.ENDPOINT_OUT)
    ei=usb.util.find_descriptor(intf,custom_match=lambda e:usb.util.endpoint_direction(e.bEndpointAddress)==usb.util.ENDPOINT_IN)
    try: dev.clear_halt(eo); dev.clear_halt(ei)
    except: pass
    was=False
    try:
        if dev.is_kernel_driver_active(0): dev.detach_kernel_driver(0); was=True
    except: pass
    usb.util.claim_interface(dev,0)
    return eo,ei,was

ep_out,ep_in,was=claim()
TAG=[0x11223344]
def send_cbw(cdb,flags,xfer):
    h=b"USBC"+struct.pack("<II",TAG[0],xfer)+struct.pack("<BBB",flags,0,len(cdb))
    cbw=h+cdb.ljust(16,b"\x00"); assert len(cbw)==31
    dev.write(ep_out,cbw,3000); TAG[0]+=1
def cam_struct(code,pl=0x30,extra=b""):
    s=bytearray(68); struct.pack_into("<H",s,4,0x2c); s[0x0b]=code
    struct.pack_into("<I",s,0x1c,pl); s[0x20:0x20+len(extra)]=extra; return bytes(s)
def pid():
    d=usb.core.find(idVendor=VEND,idProduct=0x994)
    return 0x994 if d else None

# 1) capture query (code 0x12) response: send OUT then read IN
s68=cam_struct(0x12)
send_cbw(bytes([0x7a,0,0,0,0x0d,0x44,0,0,0x60,0x08,0,0,0,0,0,0]),0x00,len(s68))
dev.write(ep_out,s68,3000)
csw=dev.read(ep_in,13,3000); print("query OUT csw status",csw[12] if len(csw)==13 else "?")
# now read response (IN)
try:
    send_cbw(bytes([0x7a,0,0,0,0x0d,0x44,0,0,0x60,0x08,0,0,0,0,0,0]),0x80,68)
    resp=dev.read(ep_in,68,3000)
    print("query IN resp:",bytes(resp).hex())
except Exception as e:
    print("query IN err",str(e)[:50])
try: dev.reset(); time.sleep(0.5)
except: pass
ep_out,ep_in,was=claim()

# 2) scan struct command codes for PID flip to 0x994 (enter updater mode)
print("\n--- scanning struct codes 0x00..0xFF for updater-mode entry (PID 0x994) ---")
import usb.core as _uc
def pid_now():
    d=_uc.find(idVendor=VEND,idProduct=0x994)
    return 0x994 if d else None
for code in range(0x100):
    s68=cam_struct(code)
    try:
        send_cbw(bytes([0x7a,0,0,0,0x0d,0x44,0,0,0x60,0x08,0,0,0,0,0,0]),0x00,len(s68))
        dev.write(ep_out,s68,2000)
        csw=dev.read(ep_in,13,2000)
        st=csw[12] if len(csw)==13 else -1
        time.sleep(0.4)
        if pid_now()==0x994:
            print("*** UPDATER MODE ENTERED via struct code=%#04x (csw status %d)"%(code,st))
            break
    except Exception as e:
        pass
    try: dev.reset(); time.sleep(0.15)
    except: pass
    if code%48==0: print("  scanned to code=%#04x pid=%s"%(code, hex(pid_now()) if pid_now() else "0x0d95"))
print("final pid:", hex(pid_now()) if pid_now() else "0x0d95 (normal)")

usb.util.release_interface(dev,0)
if was:
    try: dev.attach_kernel_driver(0)
    except: pass
