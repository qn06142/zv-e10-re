#!/usr/bin/env python3
"""
Pull live diagnostic logs, kernel ring buffer, and Sony system event records
from Sony ZV-E10 after Revision 4.3 stream start attempt.
"""

from pathlib import Path
import hashlib
import io
import json
import re
import sys
import time

REPO = Path(r"D:\02_Development_And_Projects\pmca-re")
sys.path[:0] = [str(REPO / "research" / "common"), str(REPO)]
import senser_fix  # noqa: F401
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend

i = 1
while (REPO / '.local/outputs' / "hd-v43" / f"diagnostic-{i:02d}").exists() and any((REPO / '.local/outputs' / "hd-v43" / f"diagnostic-{i:02d}").iterdir()):
    i += 1
OUT_DIR = REPO / '.local/outputs' / "hd-v43" / f"diagnostic-{i:02d}"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_REMOTE_DIR = "/log/yuy2_1080_v43chunk"


def pump_terminal(raw, seconds=10.0, quiet_after=1.5, marker=None):
    """Drain terminal output until quiet or marker matched."""
    buf = bytearray()
    last = time.monotonic()
    end = time.monotonic() + seconds
    marker_pattern = rf"^{re.escape(marker)} [0-9]+\r?$" if marker else None

    while time.monotonic() < end:
        chunk = raw.readTerminal()
        if chunk:
            buf.extend(chunk)
            last = time.monotonic()
            end = time.monotonic() + seconds
            decoded = buf.decode("latin1", "replace")
            if marker_pattern and re.search(marker_pattern, decoded, re.M):
                break
        elif (time.monotonic() - last) > quiet_after and not marker:
            break
        else:
            time.sleep(0.02)
    return buf.decode("latin1", "replace")


def run_command(raw, cmd, marker, timeout=30.0):
    """Send command to ash shell and wait for completion marker."""
    full_cmd = f"{cmd}; echo {marker} $?\n"
    raw.writeTerminal(full_cmd.encode("ascii"))
    out = pump_terminal(raw, seconds=timeout, marker=marker)
    return out


def pull_diagnostics(dev):
    SenserPlatformBackend(dev).start()
    raw = dev.dev
    dev.setTerminalEnable(False)
    dev.setTerminalEnable(True)
    pump_terminal(raw, 2.0)

    print("[*] Collecting live system and kernel state...")
    state_cmds = [
        "cat /proc/uptime",
        "cat /proc/sys/kernel/random/boot_id",
        "cat /proc/ssboot/state",
        f"ls -la {TARGET_REMOTE_DIR}",
        f"cat {TARGET_REMOTE_DIR}/runtime.log 2>/dev/null || echo NO_RUNTIME_LOG",
        f"cat {TARGET_REMOTE_DIR}/vga.log 2>/dev/null || echo NO_VGA_LOG",
        "cat /log/runtime.log 2>/dev/null || echo NO_ROOT_RUNTIME_LOG",
        "cat /log/vga.log 2>/dev/null || echo NO_ROOT_VGA_LOG",
        "ls -la /usr/share/yuy2-recovery-v43chunk",
        "cat /proc/$(/bin/busybox pidof im.elf)/maps 2>/dev/null || echo NO_IM_ELF_MAPS",
        "dmesg",
    ]

    combined_state_log = ""
    for idx, cmd in enumerate(state_cmds):
        marker = f"STATE_CMD_{idx:02d}"
        print(f"  [{idx+1}/{len(state_cmds)}] {cmd}...")
        log = run_command(raw, cmd, marker, timeout=20.0)
        combined_state_log += f"=== $ {cmd} ===\n{log}\n\n"

    (OUT_DIR / "001-state.log").write_text(combined_state_log, encoding="latin1")
    print(f"[+] Saved system state to {OUT_DIR / '001-state.log'}")

    # Pull binary log files from camera flash
    binary_pulls = [
        ("/log/AccessLog.dat", OUT_DIR / "AccessLog.dat"),
        ("/log/kikilog.dat", OUT_DIR / "kikilog.dat"),
        (f"{TARGET_REMOTE_DIR}/runtime.log", OUT_DIR / "runtime.log"),
        (f"{TARGET_REMOTE_DIR}/vga.log", OUT_DIR / "vga.log"),
    ]

    for remote_path, local_path in binary_pulls:
        try:
            print(f"[*] Downloading {remote_path}...")
            buf = io.BytesIO()
            dev.readFile(remote_path, buf)
            data = buf.getvalue()
            local_path.write_bytes(data)
            print(f"  [+] Saved {local_path.name} ({len(data)} bytes, MD5: {hashlib.md5(data).hexdigest()})")
        except Exception as e:
            print(f"  [-] Failed to download {remote_path}: {e}")

    # Generate a brief report
    summary = {
        "status": "DIAGNOSTICS_PULLED",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "files_collected": [p.name for p in OUT_DIR.glob("*") if p.is_file()],
    }
    (OUT_DIR / "status.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"[+] Diagnostic collection complete! Output in {OUT_DIR}")

    try:
        dev.setTerminalEnable(False)
    except Exception:
        pass


def main():
    print("=== Pulling Diagnostics from Sony ZV-E10 ===")
    senserShellCommand(complete=pull_diagnostics)
    return 0


if __name__ == "__main__":
    sys.exit(main())
