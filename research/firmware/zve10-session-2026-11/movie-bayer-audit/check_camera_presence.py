"""Read Windows present USB device IDs without opening device interfaces."""
import ctypes as c,json
from ctypes import wintypes as w
class GUID(c.Structure):
 _fields_=[('Data1',w.DWORD),('Data2',w.WORD),('Data3',w.WORD),('Data4',c.c_ubyte*8)]
class INFO(c.Structure):
 _fields_=[('cbSize',w.DWORD),('ClassGuid',GUID),('DevInst',w.DWORD),('Reserved',c.c_size_t)]
dll=c.WinDLL('setupapi',use_last_error=True)
dll.SetupDiGetClassDevsW.argtypes=[c.POINTER(GUID),w.LPCWSTR,w.HWND,w.DWORD];dll.SetupDiGetClassDevsW.restype=w.HANDLE
dll.SetupDiEnumDeviceInfo.argtypes=[w.HANDLE,w.DWORD,c.POINTER(INFO)];dll.SetupDiEnumDeviceInfo.restype=w.BOOL
dll.SetupDiGetDeviceInstanceIdW.argtypes=[w.HANDLE,c.POINTER(INFO),w.LPWSTR,w.DWORD,c.POINTER(w.DWORD)];dll.SetupDiGetDeviceInstanceIdW.restype=w.BOOL
dll.SetupDiDestroyDeviceInfoList.argtypes=[w.HANDLE];dll.SetupDiDestroyDeviceInfoList.restype=w.BOOL
handle=dll.SetupDiGetClassDevsW(None,'USB',None,0x2|0x4)
if handle==c.c_void_p(-1).value:raise OSError(c.get_last_error(),'SetupDiGetClassDevsW failed')
ids=[];errors=[]
try:
 index=0
 while True:
  info=INFO();info.cbSize=c.sizeof(info)
  if not dll.SetupDiEnumDeviceInfo(handle,index,c.byref(info)):
   error=c.get_last_error()
   if error!=259:errors.append(dict(operation='enumerate',error=error))
   break
  buf=c.create_unicode_buffer(4096);needed=w.DWORD()
  if dll.SetupDiGetDeviceInstanceIdW(handle,c.byref(info),buf,len(buf),c.byref(needed)):ids.append(buf.value)
  else:errors.append(dict(operation='instance_id',index=index,error=c.get_last_error()))
  index+=1
finally:dll.SetupDiDestroyDeviceInfoList(handle)
print(json.dumps(dict(method='SetupAPI present USB device-instance enumeration',present_usb_count=len(ids),sony_ids=[x for x in ids if 'VID_054C' in x.upper()],errors=errors,device_interfaces_opened=False),indent=2))
