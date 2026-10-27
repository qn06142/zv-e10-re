import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import research.device.zve10_retry as zve10

cmds = [
    "/bin/busybox md5sum /usr/share/app/color_cmn.uxc",
    "/bin/busybox md5sum /usr/share/app/Sony_DI_Icons.ttf 2>/dev/null",
    "/bin/busybox ls -la /system",
    "/bin/busybox ls -la /etc",
    "/bin/busybox md5sum /setting/Backup.bin /setting/Backup.bak /setting/Backup.orig 2>/dev/null",
]
out, _ = zve10.run(cmds)
print(out)
