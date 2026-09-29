
import struct, usb.core, usb.util, usb.backend.libusb0 as lu0
b=lu0.get_backend(); d=usb.core.find(backend=b, idVendor=0x054c, idProduct=0x0d95)
cfg=d.get_active_configuration(); itf=cfg[(0,0)]
def bulk(dirin):
    for ep in itf:
        if (ep.bmAttributes&3)==usb.util.ENDPOINT_TYPE_BULK and \
           ((ep.bEndpointAddress&0x80)!=0)==dirin: return ep
epi,epo=bulk(True),bulk(False)
try: usb.util.claim_interface(d,0)
except Exception as e: print("claim:",e)
tag=[0]
def scsi(cdb, dlen=0, dirin=True):
    tag[0]+=1
    cbw=struct.pack('<IIIBBB16s',0x43425355,tag[0],dlen,0x80 if dirin else 0,0,len(cdb),bytes(cdb).ljust(16,b'\0'))
    d.write(epo.bEndpointAddress,cbw,3000)
    data=b''
    if dlen: data=bytes(d.read(epi.bEndpointAddress,dlen,5000))
    csw=bytes(d.read(epi.bEndpointAddress,13,5000))
    sig,t,res,st=struct.unpack('<IIIB',csw[:13])
    return st,data
st,data=scsi([0x12,0,0,0,36],36)
print("INQUIRY status",st,"vendor=%r product=%r rev=%r"%(data[8:16],data[16:32],data[32:36]))
st,data=scsi([0x25]+[0]*9,8)
if len(data)==8:
    lba,bl=struct.unpack('>II',data); print("CAPACITY status",st,"lba=%d blocklen=%d => %.1f MB"%(lba,bl,(lba+1)*bl/1e6))
usb.util.release_interface(d,0)
