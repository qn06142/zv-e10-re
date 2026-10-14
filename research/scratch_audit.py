from pathlib import Path
import struct
import re

HERE = Path("D:/02_Development_And_Projects/pmca-re")
mpr_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libmpr.so"
obj_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

with open(mpr_path, "rb") as f:
    mpr_data = f.read()

with open(obj_path, "rb") as f:
    obj_data = f.read()

print("=== Scanning libmpr.so for SPS / Stride / Macroblock / Crop strings ===")
for m in re.finditer(b"(?i)(crop|stride|macroblock|pic_width|sps|avcc|frame_crop|pitch)", mpr_data):
    s = mpr_data[max(0, m.start() - 20):min(len(mpr_data), m.end() + 40)]
    # filter readable ASCII
    cleaned = bytes([c if 0x20 <= c <= 0x7e else ord('.') for c in s]).decode('latin-1')
    print(f"libmpr @ 0x{m.start():06x}: {cleaned}")
