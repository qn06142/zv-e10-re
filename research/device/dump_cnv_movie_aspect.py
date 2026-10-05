from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent.parent.parent
lib_mprctrl_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libmprctrl.so"

with open(lib_mprctrl_path, "rb") as f:
    data = f.read()

# 0x024a5c: ldr r3, [pc, #0xc] -> address is (0x24a5c & ~3) + 4 + 0xc = 0x24a6c
rel_off = struct.unpack_from("<I", data, 0x24a6c)[0]
table_addr = 0x24a5e + 4 + rel_off
print(f"rel_off = 0x{rel_off:x}, table_addr = 0x{table_addr:06x}")

print("=== Table at table_addr ===")
for i in range(5):
    entry = struct.unpack_from("<I", data, table_addr + i*4)[0]
    print(f"  [{i}] -> {entry}")
