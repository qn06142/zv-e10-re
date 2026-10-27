import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import research.device.zve10_retry as zve10

cmds = [
    # Read offset 0xc12e8 (791272 decimal) in Backup.bin and Backup.orig
    "/bin/busybox dd if=/setting/Backup.bin bs=1 skip=791270 count=16 2>/dev/null | /bin/busybox xxd -p",
    "/bin/busybox dd if=/setting/Backup.orig bs=1 skip=791270 count=16 2>/dev/null | /bin/busybox xxd -p",
    # Read offset 0xc1bc0 (793536 decimal) in Backup.bin and Backup.orig
    "/bin/busybox dd if=/setting/Backup.bin bs=1 skip=793530 count=16 2>/dev/null | /bin/busybox xxd -p",
    "/bin/busybox dd if=/setting/Backup.orig bs=1 skip=793530 count=16 2>/dev/null | /bin/busybox xxd -p",
]
out, _ = zve10.run(cmds)
print(out)
