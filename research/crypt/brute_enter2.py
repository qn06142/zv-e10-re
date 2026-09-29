import usb.core, usb.util, struct, time
VEND=0x054c
dev=usb.core.find(idVendor=VEND,idProduct=0x0d95); assert dev
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
def pid994():
    return usb.core.find(idVendor=VEND,idProduct=0x994) is not None
def identify_struct():
    s=bytearray(28)
    struct.pack_into("<I",s,0,0x20)   # length field @0
    struct.pack_into("<I",s,8,0x860)  # @8
    struct.pack_into("<I",s,0xc,0x440d)# @c
    return bytes(s)
s28=identify_struct()
print("identify struct:",s28.hex())
# read response first (IN) to see what camera returns
try:
    send_cbw(bytes([0x7a,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]),0x80,28)
    dev.write(ep_out,s28,2000)
    resp=dev.read(ep_in,28,2000)
    print("identify IN (op 0x7a) resp:",bytes(resp).hex())
except Exception as e: print("identify IN err",str(e)[:40])
try: dev.reset(); time.sleep(0.3)
except: pass
ep_out,ep_in,was=claim()
print("--- brute opcode for identify struct, watch PID 0x994 ---")
hit=None
for op in range(256):
    try:
        send_cbw(bytes([op]+[0]*15),0x00,28)
        dev.write(ep_out,s28,2000)
        csw=dev.read(ep_in,13,2000)
        st=csw[12] if len(csw)==13 else -1
        time.sleep(0.3)
        if pid994():
            print("*** UPDATER MODE via opcode=%#04x (csw %d)"%(op,st)); hit=op; break
    except Exception: pass
    try: dev.reset(); time.sleep(0.1)
    except: pass
    if op%64==0: print("  op=%#04x pid=%s"%(op,"0x994!!" if pid994() else "0x0d95"))
print("RESULT hit=",hex(hit) if hit else None)
usb.util.release_interface(dev,0)
if was:
    try: dev.attach_kernel_driver(0)
    except: pass
