import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import research.device.zve10_retry as zve10

cmds = [
    "/bin/busybox sed 30q /etc/apply_opengate.sh 2>/dev/null",
    "/bin/busybox sed 30q /etc/run_all_patches.sh 2>/dev/null"
]
out, _ = zve10.run(cmds)
print(out)
