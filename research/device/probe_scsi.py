import ctypes, ctypes.wintypes as wt

IOCTL_SCSI_PASS_THROUGH_DIRECT = 0x4D014
kernel32 = ctypes.windll.kernel32

class SCSI_PASS_THROUGH_DIRECT(ctypes.Structure):
    _fields_ = [
        ("Length",            ctypes.c_ushort),
        ("ScsiStatus",        ctypes.c_ubyte),
        ("PathId",            ctypes.c_ubyte),
        ("TargetId",          ctypes.c_ubyte),
        ("Lun",               ctypes.c_ubyte),
        ("CdbLength",         ctypes.c_ubyte),
        ("SenseInfoLength",   ctypes.c_ubyte),
        ("DataIn",            ctypes.c_ubyte),   # 0=out(to dev),1=in(from dev),2=none
        ("DataTransferLength",ctypes.c_ulong),
        ("TimeOutValue",      ctypes.c_ulong),
        ("DataBuffer",        ctypes.c_void_p),
        ("SenseInfoOffset",   ctypes.c_ulong),
        ("Cdb",               ctypes.c_ubyte * 16),
    ]

GENERIC_READ=0x80000000; GENERIC_WRITE=0x40000000; OPEN_EXISTING=3
FILE_SHARE_READ=1; FILE_SHARE_WRITE=2
print("sizeof SPT_DIRECT =", ctypes.sizeof(SCSI_PASS_THROUGH_DIRECT))

def send(dev, cdb, in_len, data_in=1, target=0, lun=0, tout=5):
    buf = ctypes.create_string_buffer(in_len) if in_len else ctypes.create_string_buffer(1)
    spt = SCSI_PASS_THROUGH_DIRECT()
    n = ctypes.sizeof(SCSI_PASS_THROUGH_DIRECT)
    spt.Length = n
    spt.PathId = 0
    spt.TargetId = target
    spt.Lun = lun
    spt.CdbLength = len(cdb)
    spt.SenseInfoLength = 0
    spt.DataIn = data_in
    spt.DataTransferLength = in_len
    spt.TimeOutValue = tout
    spt.DataBuffer = ctypes.cast(buf, ctypes.c_void_p) if in_len else 0
    spt.SenseInfoOffset = 0
    for i,b in enumerate(cdb): spt.Cdb[i]=b
    rb = ctypes.create_string_buffer(n)
    ctypes.memmove(rb, ctypes.byref(spt), n)
    h = kernel32.CreateFileW("\\\\.\\"+dev, GENERIC_READ|GENERIC_WRITE,
                             FILE_SHARE_READ|FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
    if h in (0,-1,None):
        return ("openfail", kernel32.GetLastError())
    ret = ctypes.c_ulong(0)
    ok = kernel32.DeviceIoControl(h, IOCTL_SCSI_PASS_THROUGH_DIRECT,
                                  rb, n, rb, n, ctypes.byref(ret), None)
    ker = kernel32.GetLastError()
    kernel32.CloseHandle(h)
    if not ok:
        return ("ioctl_fail", ker)
    # read back spt to get ScsiStatus
    s2 = SCSI_PASS_THROUGH_DIRECT.from_buffer_copy(rb[:n])
    resp = bytes(buf.raw[:in_len]) if in_len else b""
    return ("ok", s2.ScsiStatus, resp)

# Try several CDBs against E:
for cdb in [
    bytes([0x12,0,0,0,96,0]),          # INQUIRY
    bytes([0x00,0,0,0,0,0]),           # TEST UNIT READY
    bytes([0x25,0,0,0,0,0]),           # READ CAPACITY(10)
    bytes([0x5a,0,0x3f,0,0,0,0,0,0xc,0]), # MODE SENSE(10)
]:
    print("CDB", cdb.hex(), "->", send("E:", cdb, 96))
