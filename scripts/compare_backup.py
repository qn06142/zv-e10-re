import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import research.device.zve10_retry as zve10

cmds = [
    "/bin/busybox cmp -l /setting/Backup.orig /setting/Backup.bin | /bin/busybox head -n 30 2>/dev/null",
    "/bin/busybox cmp -l /setting/Backup.orig /setting/Backup.bin | /bin/busybox wc -l"
]
out, _ = zve10.run(cmds)
print(out)
