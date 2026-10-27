import sys
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import research.device.zve10_retry as zve10

local_lib = Path("dumps/camera_2025/usr/usr/lib")
so_files = [f.name for f in local_lib.glob("*.so")]

cmds = [f"/bin/busybox md5sum /usr/lib/{f}" for f in so_files]

out_total = ""
for i in range(0, len(cmds), 20):
    batch = cmds[i:i+20]
    out, _ = zve10.run(batch)
    out_total += out + "\n"

diffs = []
for line in out_total.splitlines():
    parts = line.strip().split()
    if len(parts) == 2 and len(parts[0]) == 32:
        remote_md5, path = parts
        fname = Path(path).name
        local_file = local_lib / fname
        if local_file.exists():
            local_md5 = hashlib.md5(local_file.read_bytes()).hexdigest()
            if remote_md5 != local_md5:
                diffs.append((fname, remote_md5, local_md5))

print("=== DIFFERING .SO FILES IN /usr/lib ===")
for fname, rem, loc in diffs:
    print(f"  {fname}: remote={rem} != local_stock={loc}")
if not diffs:
    print("  None! All other .so files match stock.")
