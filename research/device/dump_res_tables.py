from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent.parent.parent
lib_obj_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

with open(lib_obj_path, "rb") as f:
    data = f.read()

# 0x2617b2: ldr r2, [pc, #0x274]; add r2, pc
# target offset = (0x2617b2 & ~3) + 4 + 0x274 = 0x261a28
off_val = struct.unpack_from("<I", data, 0x261a28)[0]
table1 = 0x2617b8 + 4 + off_val
print(f"Table 1 at 0x{table1:06x}:")
for i in range(20):
    w = struct.unpack_from("<H", data, table1 + i*4)[0]
    h = struct.unpack_from("<H", data, table1 + i*4 + 2)[0]
    if w == 0xffff or h == 0xffff:
        print(f"  [End of table: 0x{w:04x}, 0x{h:04x}]")
        break
    print(f"  [{i}]: {w} x {h}")

# 0x261872: ldr r3, [pc, #0x1c0]; add r3, pc
# target offset = (0x261872 & ~3) + 4 + 0x1c0 = 0x261a34
off_val2 = struct.unpack_from("<I", data, 0x261a34)[0]
table2 = 0x261878 + 4 + off_val2
print(f"\nTable 2 at 0x{table2:06x}:")
for i in range(20):
    w = struct.unpack_from("<H", data, table2 + i*4)[0]
    h = struct.unpack_from("<H", data, table2 + i*4 + 2)[0]
    if w == 0xffff or h == 0xffff:
        print(f"  [End of table: 0x{w:04x}, 0x{h:04x}]")
        break
    print(f"  [{i}]: {w} x {h}")
