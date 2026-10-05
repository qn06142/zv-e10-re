with open('dumps/camera_2025/usr/usr/lib/libObj.so', 'rb') as f:
    f.seek(0x1369000)
    data = f.read(0x250)
import struct

print("=== Structure before 0x1369220 ===")
for off in range(0, len(data), 8):
    w1, w2 = struct.unpack_from('<II', data, off)
    print(f"0x{0x1369000+off:07x}: 0x{w1:08x}  0x{w2:08x}")
