import struct
from pathlib import Path
import glob

HERE = Path(__file__).resolve().parent.parent.parent
lib_dir = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib"
bin_dir = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "bin"
avcam_path = HERE / "dumps" / "av-cam.bin"

def search_int32(val, name="val"):
    target_le = struct.pack("<I", val)
    target_be = struct.pack(">I", val)
    print(f"=== Searching for 0x{val:08x} ({name}) ===")
    
    # 1. Search in av-cam.bin
    if avcam_path.exists():
        data = avcam_path.read_bytes()
        pos = 0
        while True:
            idx = data.find(target_le, pos)
            if idx == -1: break
            print(f"  av-cam.bin @ 0x{idx:08x} (LE)")
            pos = idx + 1
        pos = 0
        while True:
            idx = data.find(target_be, pos)
            if idx == -1: break
            print(f"  av-cam.bin @ 0x{idx:08x} (BE)")
            pos = idx + 1
            
    # 2. Search in libObj.so and other libs
    for fpath in list(lib_dir.glob("*.so")) + list(bin_dir.glob("*.elf")):
        data = fpath.read_bytes()
        pos = 0
        found = []
        while True:
            idx = data.find(target_le, pos)
            if idx == -1: break
            found.append(f"0x{idx:08x}")
            pos = idx + 1
        if found:
            print(f"  {fpath.name}: {len(found)} occurrences: {', '.join(found[:8])}")

if __name__ == "__main__":
    search_int32(0x0055001f, "MSG_0055001f")
    search_int32(0x010ea858, "PARAMID_MOVIE_ASPECT_RATIO")
    search_int32(0x010ea82b, "PARAMID_MOVIE_SIZE")
