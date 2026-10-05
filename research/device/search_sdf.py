from pathlib import Path
import re

HERE = Path(__file__).resolve().parent.parent.parent
lib_dir = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib"
bin_dir = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "bin"
avcam_path = HERE / "dumps" / "av-cam.bin"

def search_pattern(patt):
    print(f"=== Searching for pattern: {patt} ===")
    if avcam_path.exists():
        data = avcam_path.read_bytes()
        matches = list(re.finditer(patt.encode('ascii'), data))
        if matches:
            print(f"  av-cam.bin: {len(matches)} matches (e.g. 0x{matches[0].start():08x})")
            for m in matches[:5]:
                ctx = data[m.start():m.start()+60].split(b'\x00')[0]
                print(f"    0x{m.start():08x}: {ctx.decode('ascii', errors='replace')}")

    for fpath in list(lib_dir.glob("*.so")) + list(bin_dir.glob("*.elf")):
        data = fpath.read_bytes()
        matches = list(re.finditer(patt.encode('ascii'), data))
        if matches:
            print(f"  {fpath.name}: {len(matches)} matches")
            for m in matches[:3]:
                ctx = data[m.start():m.start()+60].split(b'\x00')[0]
                print(f"    0x{m.start():08x}: {ctx.decode('ascii', errors='replace')}")

if __name__ == "__main__":
    search_pattern("SensorDriver")
    search_pattern("SDF_")
    search_pattern("Sdf")
