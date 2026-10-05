from pathlib import Path
import re

HERE = Path(__file__).resolve().parent.parent.parent
lib_obj_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

with open(lib_obj_path, "rb") as f:
    data = f.read()

matches = re.findall(b'N11OBJRENDERER[0-9a-zA-Z_]+E', data)
unique_matches = sorted(list(set(m.decode('ascii') for m in matches)))
print(f"Found {len(unique_matches)} OBJRENDERER classes:")
for m in unique_matches:
    print(f"  {m}")
