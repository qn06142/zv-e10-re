import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
lib_obj_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

with open(lib_obj_path, "rb") as f:
    data = f.read()

def find_refs(target):
    target_le = struct.pack("<I", target)
    pos = 0
    print(f"=== Searching for references to 0x{target:08x} ===")
    while True:
        idx = data.find(target_le, pos)
        if idx == -1: break
        print(f"  found at 0x{idx:08x}")
        pos = idx + 1

if __name__ == "__main__":
    find_refs(0x01369224)
    find_refs(0x01369220)
    find_refs(0x01369200)
