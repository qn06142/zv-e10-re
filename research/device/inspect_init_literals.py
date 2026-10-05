import struct

with open("dumps/staged/audit/init", "rb") as f:
    data = f.read()

for va in range(0x9fc8, 0xa034, 4):
    off = va - 0x8000
    val = struct.unpack("<I", data[off:off+4])[0]
    str_val = ""
    if 0x8000 <= val < 0x8000 + len(data):
        s_off = val - 0x8000
        s_end = data.find(b"\x00", s_off)
        str_val = data[s_off:s_end].decode("latin1", errors="ignore")
    print(f"0x{va:x}: 0x{val:08x} -> {repr(str_val)}")
