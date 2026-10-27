"""Native Windows WinUSB driver backend for Sony camera service mode without Zadig."""

import ctypes
from ctypes import windll, byref, c_ubyte, c_ulong, c_ushort, c_void_p, POINTER, create_string_buffer, sizeof
from ctypes.wintypes import BOOL, HANDLE, DWORD
from collections import namedtuple

from comtypes import GUID

from .. import BaseUsbContext, BaseUsbDriver, UsbDeviceHandle, USB_CLASS_VENDOR_SPECIFIC
from ..generic import BaseUsbBackend, GenericUsbDriver, GenericUsbException
from . import parseDeviceId
from .setupapi import listDeviceClass, GUID_DEVINTERFACE_USB_DEVICE, INVALID_HANDLE_VALUE

WINUSB_INTERFACE_GUID = GUID('{dee824ef-729b-4a0e-9c14-b7117d33a817}')
PIPE_TRANSFER_TIMEOUT = 0x03
FILE_FLAG_OVERLAPPED = 0x40000000

Endpoint = namedtuple('Endpoint', 'bEndpointAddress, bmAttributes')


class USB_INTERFACE_DESCRIPTOR(ctypes.Structure):
    _fields_ = [
        ('bLength', c_ubyte),
        ('bDescriptorType', c_ubyte),
        ('bInterfaceNumber', c_ubyte),
        ('bAlternateSetting', c_ubyte),
        ('bNumEndpoints', c_ubyte),
        ('bInterfaceClass', c_ubyte),
        ('bInterfaceSubClass', c_ubyte),
        ('bInterfaceProtocol', c_ubyte),
        ('iInterface', c_ubyte),
    ]


class WINUSB_PIPE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('PipeType', c_ulong),
        ('PipeId', c_ubyte),
        ('MaximumPacketSize', c_ushort),
        ('Interval', c_ubyte),
    ]


class WINUSB_SETUP_PACKET(ctypes.Structure):
    _fields_ = [
        ('RequestType', c_ubyte),
        ('Request', c_ubyte),
        ('Value', c_ushort),
        ('Index', c_ushort),
        ('Length', c_ushort),
    ]


_CreateFile = windll.kernel32.CreateFileW
_CreateFile.restype = HANDLE
_CreateFile.argtypes = [ctypes.c_wchar_p, DWORD, DWORD, c_void_p, DWORD, DWORD, HANDLE]

_CloseHandle = windll.kernel32.CloseHandle
_CloseHandle.restype = BOOL
_CloseHandle.argtypes = [HANDLE]

_WinUsb_Initialize = windll.winusb.WinUsb_Initialize
_WinUsb_Initialize.restype = BOOL
_WinUsb_Initialize.argtypes = [HANDLE, POINTER(HANDLE)]

_WinUsb_Free = windll.winusb.WinUsb_Free
_WinUsb_Free.restype = BOOL
_WinUsb_Free.argtypes = [HANDLE]

_WinUsb_QueryInterfaceSettings = windll.winusb.WinUsb_QueryInterfaceSettings
_WinUsb_QueryInterfaceSettings.restype = BOOL
_WinUsb_QueryInterfaceSettings.argtypes = [HANDLE, c_ubyte, POINTER(USB_INTERFACE_DESCRIPTOR)]

_WinUsb_QueryPipe = windll.winusb.WinUsb_QueryPipe
_WinUsb_QueryPipe.restype = BOOL
_WinUsb_QueryPipe.argtypes = [HANDLE, c_ubyte, c_ubyte, POINTER(WINUSB_PIPE_INFORMATION)]

_WinUsb_ReadPipe = windll.winusb.WinUsb_ReadPipe
_WinUsb_ReadPipe.restype = BOOL
_WinUsb_ReadPipe.argtypes = [HANDLE, c_ubyte, c_void_p, c_ulong, POINTER(c_ulong), c_void_p]

_WinUsb_WritePipe = windll.winusb.WinUsb_WritePipe
_WinUsb_WritePipe.restype = BOOL
_WinUsb_WritePipe.argtypes = [HANDLE, c_ubyte, c_void_p, c_ulong, POINTER(c_ulong), c_void_p]

_WinUsb_ControlTransfer = windll.winusb.WinUsb_ControlTransfer
_WinUsb_ControlTransfer.restype = BOOL
_WinUsb_ControlTransfer.argtypes = [HANDLE, WINUSB_SETUP_PACKET, c_void_p, c_ulong, POINTER(c_ulong), c_void_p]

_WinUsb_SetPipePolicy = windll.winusb.WinUsb_SetPipePolicy
_WinUsb_SetPipePolicy.restype = BOOL
_WinUsb_SetPipePolicy.argtypes = [HANDLE, c_ubyte, c_ulong, c_ulong, c_void_p]

_WinUsb_ResetPipe = getattr(windll.winusb, 'WinUsb_ResetPipe', None)
if _WinUsb_ResetPipe:
    _WinUsb_ResetPipe.restype = BOOL
    _WinUsb_ResetPipe.argtypes = [HANDLE, c_ubyte]

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80


class WinUsbBackend(BaseUsbBackend):
    def __init__(self, devicePath, idVendor, idProduct):
        self._path = devicePath
        self._idVendor = idVendor
        self._idProduct = idProduct
        self._fileHandle = None
        self._winusbHandle = None
        self._endpoints = []

        self._open()

    def _open(self):
        self._fileHandle = _CreateFile(
            self._path,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OVERLAPPED,
            None,
        )
        if self._fileHandle == INVALID_HANDLE_VALUE or not self._fileHandle:
            raise GenericUsbException(f"Failed to open device at {self._path} (Win32 err {ctypes.GetLastError()})")

        winusb = HANDLE()
        if not _WinUsb_Initialize(self._fileHandle, byref(winusb)):
            _CloseHandle(self._fileHandle)
            self._fileHandle = None
            raise GenericUsbException(f"WinUsb_Initialize failed (Win32 err {ctypes.GetLastError()})")
        self._winusbHandle = winusb

        desc = USB_INTERFACE_DESCRIPTOR()
        if _WinUsb_QueryInterfaceSettings(self._winusbHandle, 0, byref(desc)):
            for i in range(desc.bNumEndpoints):
                pipe = WINUSB_PIPE_INFORMATION()
                if _WinUsb_QueryPipe(self._winusbHandle, 0, i, byref(pipe)):
                    self._endpoints.append(Endpoint(pipe.PipeId, pipe.PipeType))
                    timeout_ms = c_ulong(5000)
                    _WinUsb_SetPipePolicy(
                        self._winusbHandle, pipe.PipeId, PIPE_TRANSFER_TIMEOUT, sizeof(timeout_ms), byref(timeout_ms)
                    )

    def close(self):
        if self._winusbHandle:
            _WinUsb_Free(self._winusbHandle)
            self._winusbHandle = None
        if self._fileHandle and self._fileHandle != INVALID_HANDLE_VALUE:
            _CloseHandle(self._fileHandle)
            self._fileHandle = None

    def __del__(self):
        self.close()

    def getId(self):
        return self._idVendor, self._idProduct

    def getEndpoints(self):
        return self._endpoints

    def reset(self):
        if _WinUsb_ResetPipe and self._winusbHandle:
            for ep in self._endpoints:
                _WinUsb_ResetPipe(self._winusbHandle, ep.bEndpointAddress)

    def clearHalt(self, ep):
        if _WinUsb_ResetPipe and self._winusbHandle:
            _WinUsb_ResetPipe(self._winusbHandle, ep)

    def read(self, ep, length, timeout=None):
        if not self._winusbHandle:
            raise GenericUsbException("Device not open")
        if timeout:
            t = c_ulong(timeout)
            _WinUsb_SetPipePolicy(self._winusbHandle, ep, PIPE_TRANSFER_TIMEOUT, sizeof(t), byref(t))

        buf = create_string_buffer(length)
        transferred = c_ulong(0)
        if not _WinUsb_ReadPipe(self._winusbHandle, ep, buf, length, byref(transferred), None):
            raise GenericUsbException(f"WinUsb_ReadPipe failed on EP 0x{ep:02x} (err {ctypes.GetLastError()})")
        return buf.raw[:transferred.value]

    def write(self, ep, data):
        if not self._winusbHandle:
            raise GenericUsbException("Device not open")
        buf = create_string_buffer(data, len(data))
        transferred = c_ulong(0)
        if not _WinUsb_WritePipe(self._winusbHandle, ep, buf, len(data), byref(transferred), None):
            raise GenericUsbException(f"WinUsb_WritePipe failed on EP 0x{ep:02x} (err {ctypes.GetLastError()})")

    def classInterfaceRequestOut(self, request, value, index, data=b""):
        packet = WINUSB_SETUP_PACKET()
        packet.RequestType = 0x21  # HOST_TO_DEVICE | CLASS | INTERFACE
        packet.Request = request
        packet.Value = value
        packet.Index = index
        packet.Length = len(data)
        transferred = c_ulong(0)
        buf = create_string_buffer(data, len(data)) if data else None
        if not _WinUsb_ControlTransfer(self._winusbHandle, packet, buf, len(data), byref(transferred), None):
            raise GenericUsbException(f"WinUsb_ControlTransfer class failed (err {ctypes.GetLastError()})")

    def vendorRequestOut(self, request, value, index, data=b""):
        packet = WINUSB_SETUP_PACKET()
        packet.RequestType = 0x40  # HOST_TO_DEVICE | VENDOR | DEVICE
        packet.Request = request
        packet.Value = value
        packet.Index = index
        packet.Length = len(data)
        transferred = c_ulong(0)
        buf = create_string_buffer(data, len(data)) if data else None
        if not _WinUsb_ControlTransfer(self._winusbHandle, packet, buf, len(data), byref(transferred), None):
            raise GenericUsbException(f"WinUsb_ControlTransfer vendor failed (err {ctypes.GetLastError()})")


class WinUsbDriver(GenericUsbDriver):
    """WinUSB-backed generic USB driver that seamlessly drops into SonySenserDevice / SonySenserCamera."""
    def __init__(self, backend):
        super(WinUsbDriver, self).__init__(backend)


class VendorSpecificContext(BaseUsbContext):
    def __init__(self):
        super(VendorSpecificContext, self).__init__("Windows-WinUSB", USB_CLASS_VENDOR_SPECIFIC)

    def listDevices(self, vendor):
        # 1. Search for WinUSB interface class GUID
        seen = set()
        for guid in [WINUSB_INTERFACE_GUID]:
            try:
                for devInst, (hwid, ifaces) in listDeviceClass(guid=guid):
                    vid, pid = parseDeviceId(hwid)
                    if vid == vendor and ifaces:
                        path = ifaces[0]
                        if path not in seen:
                            seen.add(path)
                            yield UsbDeviceHandle(path, vid, pid)
            except Exception:
                pass

    def openDevice(self, device):
        backend = WinUsbBackend(device.handle, device.idVendor, device.idProduct)
        return WinUsbDriver(backend)
