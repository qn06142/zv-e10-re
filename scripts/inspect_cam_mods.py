import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import research.device.zve10_retry as zve10

cmds = [
    "/bin/busybox ls -la /setting/mode 2>/dev/null",
    "cat /setting/mode/preload 2>/dev/null",
    "cat /setting/mode/dmode 2>/dev/null",
    "/bin/busybox find /setting -maxdepth 3",
    "/bin/busybox md5sum /usr/share/app/color_cmn.uxc",
    "/bin/busybox md5sum /usr/share/app/string_english_f.uxc",
    "/bin/busybox md5sum /usr/share/fonts/Sony_DI_Icons.ttf 2>/dev/null",
    "/bin/busybox md5sum /usr/lib/libObj.so /usr/lib/libmpr.so 2>/dev/null",
]
out, _ = zve10.run(cmds)
print(out)
