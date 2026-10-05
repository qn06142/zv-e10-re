from pathlib import Path
import re

HERE = Path(__file__).resolve().parent.parent.parent
avcam_path = HERE / "dumps" / "av-cam.bin"
data = avcam_path.read_bytes()

keywords = ["ScanMode", "Aspect", "ImageArea", "MovieSize", "StillSize", "SensorMode", "TvScan", "Readout", "Crop"]

for kw in keywords:
    matches = list(re.finditer(kw.encode('ascii'), data, re.IGNORECASE))
    print(f"=== Keyword: '{kw}' ({len(matches)} matches) ===")
    for m in matches[:6]:
        # print up to 80 chars of surrounding null-terminated string
        start = data.rfind(b'\x00', 0, m.start())
        start = start + 1 if start != -1 else m.start()
        end = data.find(b'\x00', m.start())
        end = end if end != -1 else m.start() + 60
        s = data[start:end].decode('ascii', errors='replace')
        print(f"  0x{m.start():08x} (VA 0x{0x635c6000 + m.start():08x}): {s}")
