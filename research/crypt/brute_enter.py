import usb.core, usb.util, struct, time
VEND=0x054c
def find_cam():
    d=usb.core.find(idVendor=VEND,idProduct=0x0d95); return d
dev=find_cam(); assert dev
def claim():
    global dev
    try: dev.reset(); time.sleep(0.8)
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
def pid994():
    return usb.core.find(idVendor=VEND,idProduct=0x994) is not None

# brute force ONE byte at a candidate offset in the 68-byte struct
OFFSET=0x20
print("brute-forcing byte @ struct offset %#x (code 0x12, size 0x2c, len 0x30)"%OFFSET)
hit=None
for v in range(256):
    s68=bytearray(cam_struct(0x12))
    s68[OFFSET]=v
    try:
        send_cbw(bytes([0x7a,0,0,0,0x0d,0x44,0,0,0x60,0x08,0,0,0,0,0,0]),0x00,68)
        dev.write(ep_out,bytes(s68),2000)
        csw=dev.read(ep_in,13,2000)
        st=csw[12] if len(csw)==13 else -1
        time.sleep(0.35)
        if pid994():
            print("*** PID FLIP to 0x994 with byte@%#x=%#04x (csw %d)"%(OFFSET,v,st))
            hit=(OFFSET,v); break
    except Exception: pass
    try: dev.reset(); time.sleep(0.12)
    except: pass
    if v%64==0: print("  v=%#04x pid=%s"%(v, "0x994!!" if pid994() else "0x0d95"))
print("RESULT: hit=",hit)
usb.util.release_interface(dev,0)
if was:
    try: dev.attach_kernel_driver(0)
    except: pass
