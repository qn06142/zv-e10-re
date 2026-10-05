import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
lib_obj_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

with open(lib_obj_path, "rb") as f:
    data = f.read()

def read_str(addr):
    if addr < 0 or addr >= len(data):
        return f"<invalid 0x{addr:x}>"
    end = data.find(b'\x00', addr)
    if end != -1:
        return data[addr:end].decode('ascii', errors='replace')
    return "<no null>"

print("=== Strings in table 0x1369220 ===")
for offset in range(0x1369224, 0x1369400, 4):
    ptr = struct.unpack_from("<I", data, offset)[0]
    s = read_str(ptr)
    print(f"0x{offset:07x}: 0x{ptr:08x} -> {s}")
