import usb.core, usb.util, struct, time

VEND=0x054c; PROD=0x0d95
dev = usb.core.find(idVendor=VEND, idProduct=PROD)
assert dev
try: dev.reset(); time.sleep(1)
except: pass
cfg = dev.get_active_configuration(); intf = cfg[(0,0)]
ep_out = usb.util.find_descriptor(intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)==usb.util.ENDPOINT_OUT)
ep_in  = usb.util.find_descriptor(intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)==usb.util.ENDPOINT_IN)
try: dev.clear_halt(ep_out); dev.clear_halt(ep_in)
except: pass
was=False
try:
    if dev.is_kernel_driver_active(0): dev.detach_kernel_driver(0); was=True
except: pass
usb.util.claim_interface(dev, 0)

TAG=[0x11223344]
def send_cbw(cdb, flags, xfer):
    header=b"USBC"+struct.pack("<II",TAG[0],xfer)+struct.pack("<BBB",flags,0,len(cdb))
    cbw=header+cdb.ljust(16,b"\x00"); assert len(cbw)==31
    dev.write(ep_out,cbw,3000); TAG[0]+=1

def cam_struct(code, pl=0x30, extra=b""):
    s=bytearray(68); struct.pack_into("<H",s,4,0x2c); s[0x0b]=code
    struct.pack_into("<I",s,0x1c,pl); s[0x20:0x20+len(extra)]=extra; return bytes(s)

hits=[]
for code in [0x12]:
    s68=cam_struct(code)
    for op in range(0x100):
        cdb=bytearray(16); cdb[0]=op; cdb[4]=0x0d; cdb[5]=0x44; cdb[8]=0x60; cdb[9]=0x08
        try:
            send_cbw(bytes(cdb),0x00,len(s68))
            dev.write(ep_out,s68,2000)
            csw=dev.read(ep_in,13,2000)
            st=csw[12] if len(csw)==13 else -1
            if st==0:
                hits.append((code,op,"STATUS0"))
                print("*** HIT code=%#04x op=%#04x -> CSW=%s"%(code,op,bytes(csw).hex()))
        except Exception as e:
            pass
        try: dev.reset(); time.sleep(0.2)
        except: pass
print("done. hits:",hits)
usb.util.release_interface(dev,0)
if was:
    try: dev.attach_kernel_driver(0)
    except: pass
