#!/usr/bin/env python3
"""Non-destructive: report the raw size of PhysicalDrive2 (the Sony DSC MSC disk)
and dump its full contents to a file for firmware analysis.

We read via the Windows device path \\.\PhysicalDrive2 using a raw handle so we
capture EVERYTHING (filesystem + slack + any non-partitioned regions), not just
the mounted FAT16 volume. This is a read-only copy -- no writes, no unlock.
"""
import ctypes, sys, os

PD = r'\\.\PhysicalDrive2'
h = ctypes.windll.kernel32.CreateFileW(
    PD, 0x80000000,  # GENERIC_READ
    1,               # FILE_SHARE_READ
    None, 3, 0, None)
if h == -1:
    print('CreateFile failed, GetLastError =', ctypes.windll.kernel32.GetLastError())
    # try PhysicalDrive2 via alternate check
    sys.exit(1)
out = ctypes.create_string_buffer(8)
ret = ctypes.c_ulong(0)
ok = ctypes.windll.kernel32.DeviceIoControl(
    h, 0x7405C, None, 0, out, 8, ctypes.byref(ret), None)  # IOCTL_DISK_GET_LENGTH_INFO
if not ok:
    print('DeviceIoControl failed, GetLastError =', ctypes.windll.kernel32.GetLastError())
    ctypes.windll.kernel32.CloseHandle(h); sys.exit(1)
size = ctypes.c_longlong.from_buffer_copy(out).value
print('PhysicalDrive2 total size: %d bytes (%.2f MB)' % (size, size/1e6))

# Dump the whole thing (29MB is small; do it in 1MB chunks, read-only)
out_path = r'C:\Users\Minhsnguhoa\pmca-re\msc_dump.bin'
CHUNK = 65536
read = 0
with open(out_path, 'wb') as f:
    buf = ctypes.create_string_buffer(CHUNK)
    nread = ctypes.c_ulong(0)
    while read < size:
        toread = min(CHUNK, size - read)
        ok = ctypes.windll.kernel32.ReadFile(h, buf, toread, ctypes.byref(nread), None)
        if not ok or nread.value == 0:
            # device stopped returning data; stop cleanly
            break
        f.write(buf.raw[:nread.value])
        read += nread.value
ctypes.windll.kernel32.CloseHandle(h)
print('Dumped %d bytes -> %s' % (read, out_path))
