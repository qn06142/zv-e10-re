import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
lib_obj_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

with open(lib_obj_path, "rb") as f:
    data = f.read()

def dump_table():
    print("=== Table around 0x01369220 in libObj.so ===")
    start = 0x01369200
    for offset in range(start, start + 0x200, 4):
        val = struct.unpack_from("<I", data, offset)[0]
        # check if it references a string or code
        print(f"0x{offset:07x}: 0x{val:08x}")

if __name__ == "__main__":
    dump_table()
