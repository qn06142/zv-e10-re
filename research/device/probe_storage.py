import ctypes, ctypes.wintypes as wt

IOCTL_SCSI_PASS_THROUGH_DIRECT = 0x4D014
IOCTL_STORAGE_QUERY_PROPERTY    = 0x2D1400

kernel32 = ctypes.windll.kernel32

# STORAGE_PROPERTY_QUERY
class STORAGE_PROPERTY_QUERY(ctypes.Structure):
    _fields_ = [("PropertyId", ctypes.c_ulong),
                ("QueryType", ctypes.c_ulong),
                ("AdditionalParameters", ctypes.c_ubyte * 1)]
# STORAGE_DEVICE_DESCRIPTOR header (we read a big buffer)
class STORAGE_DEVICE_DESCRIPTOR(ctypes.Structure):
    _fields_ = [("Version", ctypes.c_ulong),
                ("Size", ctypes.c_ulong),
                ("DeviceType", ctypes.c_ubyte),
                ("DeviceTypeModifier", ctypes.c_ubyte),
                ("RemovableMedia", ctypes.c_ubyte),
                ("CommandQueueing", ctypes.c_ubyte),
                ("VendorIdOffset", ctypes.c_ulong),
                ("ProductIdOffset", ctypes.c_ulong),
                ("ProductRevisionOffset", ctypes.c_ulong),
                ("SerialNumberOffset", ctypes.c_ulong),
                ("BusType", ctypes.c_ulong),
                ("RawPropertiesLength", ctypes.c_ulong)]

GENERIC_READ=0x80000000; GENERIC_WRITE=0x40000000; OPEN_EXISTING=3
FILE_SHARE_READ=1; FILE_SHARE_WRITE=2

def open_dev(path):
    return kernel32.CreateFileW(path, GENERIC_READ|GENERIC_WRITE,
                                FILE_SHARE_READ|FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)

def storage_query(h):
    pq = STORAGE_PROPERTY_QUERY(); pq.PropertyId=0; pq.QueryType=0  # PropertyStandardQuery
    inb = ctypes.create_string_buffer(ctypes.sizeof(pq))
    ctypes.memmove(inb, ctypes.byref(pq), ctypes.sizeof(pq))
    outb = ctypes.create_string_buffer(1024)
    ret = ctypes.c_ulong(0)
    ok = kernel32.DeviceIoControl(h, IOCTL_STORAGE_QUERY_PROPERTY,
                                  inb, ctypes.sizeof(inb), outb, ctypes.sizeof(outb),
                                  ctypes.byref(ret), None)
    if not ok:
        return None, kernel32.GetLastError()
    sd = STORAGE_DEVICE_DESCRIPTOR.from_buffer_copy(outb[:ctypes.sizeof(STORAGE_DEVICE_DESCRIPTOR)])
    raw = outb.raw
    def getstr(off):
        if off==0: return ""
        end = raw.find(b"\x00", off)
        return raw[off:end].decode("latin1","replace")
    return {"vendor":getstr(sd.VendorIdOffset), "product":getstr(sd.ProductIdOffset),
            "rev":getstr(sd.ProductRevisionOffset), "bus":sd.BusType,
            "removable":sd.RemovableMedia}, 0

for drv in ("D:","E:"):
    path="\\\\.\\"+drv
    h=open_dev(path)
    if h in (0,-1,None):
        print("%s: open failed" % drv); continue
    print("=== %s ===" % drv)
    d,err = storage_query(h)
    if d is None:
        print("   STORAGE_QUERY failed err=%d" % err)
    else:
        print("   vendor=%r product=%r rev=%r bus=%d removable=%d" % (
            d["vendor"], d["product"], d["rev"], d["bus"], d["removable"]))
    kernel32.CloseHandle(h)
