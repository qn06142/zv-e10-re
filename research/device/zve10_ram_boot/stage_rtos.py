"""Stage an rtos.bin image to /log/zve10-ram-boot/rtos.bin over USB Senser with backup, readback, and READY check (never sends GO)."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import re
import sys

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO), str(REPO / "research/common"), str(REPO / "research/device/zve10_hardware_map")]

import senser_fix  # noqa: F401
from capture_display_state import TerminalSession
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend
from zve10_dumpall import _preflight

DIRECTORY = "/log/zve10-ram-boot"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--backup-name", default="rtos.pre-live-bayer.bin")
    parser.add_argument("--candidate-name", default="rtos.live-bayer.next")
    args = parser.parse_args()

    image = args.image.read_bytes()
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    backup = args.backup_name
    candidate = args.candidate_name
    report = {"image": str(args.image), "bytes": len(image), "commands": [], "status": "pending"}

    def stage(device):
        SenserPlatformBackend(device).start()
        device.setTerminalEnable(False)
        device.setTerminalEnable(True)
        commands = set()
        terminal = TerminalSession(device.dev, commands)

        def run(command, *, allow_failure=False, timeout=20):
            commands.add(command)
            rc, body = terminal.run(command, timeout=timeout)
            report["commands"].append([command, rc, body])
            print(command, rc, body[-180:], flush=True)
            if rc and not allow_failure:
                raise RuntimeError(f"Failed with status {rc}: {command}")
            return rc, body

        def drain():
            while device.dev.readTerminal():
                pass

        def read(name):
            data = BytesIO()
            device.readFile(DIRECTORY + "/" + name, data)
            drain()
            return data.getvalue()

        changed = installed = module_loaded = False
        existing = b""
        try:
            run(f"cd {DIRECTORY}")
            _, modules = run("busybox cat /proc/modules")
            if re.search(r"(?m)^zve10_(ram_boot|boot_bridge) ", modules):
                raise RuntimeError("Existing boot module is already loaded")
            run(f"test ! -e {candidate}")
            existing = read("rtos.bin")
            (out / "previous-rtos.bin").write_bytes(existing)
            if existing == image:
                raise RuntimeError("Requested bytes are already installed")
            rc, _ = run(f"test -e {backup}", allow_failure=True)
            if rc == 0:
                if read(backup) != existing:
                    raise RuntimeError("Existing backup differs from current rtos.bin")
            else:
                run(f"busybox cp rtos.bin {backup}", timeout=60)
                if read(backup) != existing:
                    raise RuntimeError("Backup readback mismatch")
            device.writeFile(DIRECTORY + "/" + candidate, image)
            drain()
            if read(candidate) != image:
                raise RuntimeError("Candidate readback mismatch")
            run(f"busybox mv {candidate} rtos.bin")
            changed = True
            if read("rtos.bin") != image:
                raise RuntimeError("Installed readback mismatch")
            run("echo 3 > /proc/sys/vm/drop_caches", allow_failure=True)
            run("busybox insmod ./boot.ko", timeout=35)
            module_loaded = True
            _, body = run("cat /sys/module/zve10_ram_boot/parameters/state")
            if not re.search(r"(?m)^READY\s*$", body):
                raise RuntimeError("Loader did not reach READY")
            run("busybox rmmod zve10_ram_boot")
            module_loaded = False
            run("sync")
            installed = True
            report["status"] = "READY verified and module unloaded"
        finally:
            try:
                if module_loaded:
                    run("busybox rmmod zve10_ram_boot", allow_failure=True)
                if changed and not installed:
                    run(f"busybox cp {backup} rtos.bin")
                    if read("rtos.bin") != existing:
                        raise RuntimeError("Restoration readback mismatch")
                    report["restored"] = True
            finally:
                device.setTerminalEnable(False)

    try:
        _preflight()
        senserShellCommand(complete=stage)
        if report["status"] == "pending":
            raise RuntimeError("No completed Senser staging session")
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        (out / "stage.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
