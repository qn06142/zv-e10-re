from pathlib import Path
import struct
import glob

HERE = Path(__file__).resolve().parent.parent.parent
lib_dir = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib"
bin_dir = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "bin"

target_str = b"PARAMID_MOVIE_ASPECT_RATIO"

print("Searching for 'PARAMID_MOVIE_ASPECT_RATIO' in all libs...")
for p in list(lib_dir.glob("*.so")) + list(bin_dir.glob("*.elf")):
    data = p.read_bytes()
    idx = 0
    found = []
    while True:
        pos = data.find(target_str, idx)
        if pos == -1: break
        found.append(pos)
        idx = pos + 1
    if found:
        print(f"  {p.name}: {len(found)} matches: {[hex(x) for x in found]}")
