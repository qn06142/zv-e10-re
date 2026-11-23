"""Version 1 returning Thumb payload envelope; checksum detects accidental corruption."""
import struct
import zlib


def pack(body,entry=0):
    body+=bytes((-len(body))%4)
    if not 2<=len(body)<=2048:raise ValueError('Payload size outside ABI bounds')
    if entry<0 or entry>=len(body) or entry&1:raise ValueError('Invalid Thumb entry offset')
    return b'ZVRAM001'+struct.pack('<6I',1,32,len(body),entry,zlib.crc32(body),1)+body
