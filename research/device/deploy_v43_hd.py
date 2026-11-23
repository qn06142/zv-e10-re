#!/usr/bin/env python3
"""
Deploy and verify Revision 4.3 1080p YUY2 USB 3.0 Candidate on live Sony ZV-E10.

Strict Safety Guarantees:
1. Never modifies /setting/DmmConfig.bin (enforces MD5 9f197ff9b300e49ab531b6f9e794253e).
2. Backs up original binaries to /usr/share/yuy2-recovery-v43chunk before touching /usr.
3. Cold boot required if streaming libraries are currently mapped in im.elf.
4. Atomic staging, temporary filenames, hash verification before rename.
5. Post-installation readback and byte-for-byte verification.
"""

from pathlib import Path
import hashlib
import io
import json
import os
import re
import sys
import time

REPO = Path(r"D:\02_Development_And_Projects\pmca-re")
sys.path[:0] = [str(REPO / "research" / "common"), str(REPO)]
import senser_fix  # noqa: F401
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend

OUT_DIR = REPO / '.local/outputs' / "hd-v43"
DEPLOY_DIR = OUT_DIR / "deployment"
READBACK_DIR = DEPLOY_DIR / "readback"
DEPLOY_DIR.mkdir(parents=True, exist_ok=True)
READBACK_DIR.mkdir(parents=True, exist_ok=True)

TARGET_REMOTE_DIR = "/log/yuy2_1080_v43chunk"

EXPECTED_HASHES = {
    "yuy2_1080_v43chunk.so": "fec062e0e4f5641235a5b8aa42ba1452",
    "libInfraStreamingUsb.v43.so": "4c5deb4a89474c0a3b65356f034a5d9e",
    "usbg_video.v43.ko": "9ded6930932e7db541247c4b158b93fc",
    "DmmConfig.bin": "9f197ff9b300e49ab531b6f9e794253e",
}


def pump_terminal(raw, seconds=10.0, quiet_after=1.5, marker=None, until=None):
    """Drain terminal output until quiet or completion marker regex matched."""
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
            if until and until in decoded:
                break
        elif (time.monotonic() - last) > quiet_after and not marker and not until:
            break
        else:
            time.sleep(0.02)
    return buf.decode("latin1", "replace")


def run_command(raw, cmd, marker, timeout=30.0):
    """Send command to ash shell and wait for completion marker."""
    full_cmd = f"{cmd}; echo {marker} $?\n"
    raw.writeTerminal(full_cmd.encode("ascii"))
    out = pump_terminal(raw, seconds=timeout, marker=marker)
    match = re.search(rf"^{re.escape(marker)} ([0-9]+)\r?$", out, re.M)
    if not match:
        raise RuntimeError(f"Command '{cmd}' timed out or marker '{marker}' missing.\nOutput:\n{out}")
    rc = int(match.group(1))
    if rc != 0:
        raise RuntimeError(f"Command '{cmd}' exited with code {rc}.\nOutput:\n{out}")
    return out


def deploy_session(dev):
    """Execute unified staging, validation, installation, and readback in a single session."""
    SenserPlatformBackend(dev).start()
    raw = dev.dev
    dev.setTerminalEnable(False)
    dev.setTerminalEnable(True)
    pump_terminal(raw, 2.0)

    print("[*] Creating remote staging directory:", TARGET_REMOTE_DIR)
    run_command(raw, f"/bin/busybox mkdir -p {TARGET_REMOTE_DIR}", "MKDIR_DONE")

    # Copy space-check.elf if available
    run_command(
        raw,
        f"[ -f /log/yuy2_1080_v41hd/space-check.elf ] && /bin/busybox cp /log/yuy2_1080_v41hd/space-check.elf {TARGET_REMOTE_DIR}/space-check.elf && /bin/busybox chmod 755 {TARGET_REMOTE_DIR}/space-check.elf || true",
        "SPACE_CHECK_DONE",
    )

    # Upload v43 artifacts
    uploads = [
        (OUT_DIR / "yuy2_1080_v43chunk.so", f"{TARGET_REMOTE_DIR}/yuy2_1080_v43chunk.so"),
        (OUT_DIR / "libInfraStreamingUsb.so", f"{TARGET_REMOTE_DIR}/libInfraStreamingUsb.v43.so"),
        (OUT_DIR / "usbg_video.ko", f"{TARGET_REMOTE_DIR}/usbg_video.v43.ko"),
        (OUT_DIR / "install.sh", f"{TARGET_REMOTE_DIR}/install.sh"),
        (OUT_DIR / "rollback.sh", f"{TARGET_REMOTE_DIR}/rollback.sh"),
    ]

    for local_path, remote_path in uploads:
        data = local_path.read_bytes()
        print(f"[*] Uploading {local_path.name} ({len(data)} bytes) -> {remote_path}...")
        dev.writeFile(remote_path, data)

    run_command(raw, f"/bin/busybox chmod 755 {TARGET_REMOTE_DIR}/*.sh", "CHMOD_DONE")

    # Verify staged hashes
    print("[*] Verifying staged file hashes on camera...")
    verify_cmd = (
        f'[ "$(/bin/busybox md5sum {TARGET_REMOTE_DIR}/yuy2_1080_v43chunk.so | /bin/busybox cut -d " " -f 1)" = "{EXPECTED_HASHES["yuy2_1080_v43chunk.so"]}" ] && '
        f'[ "$(/bin/busybox md5sum {TARGET_REMOTE_DIR}/libInfraStreamingUsb.v43.so | /bin/busybox cut -d " " -f 1)" = "{EXPECTED_HASHES["libInfraStreamingUsb.v43.so"]}" ] && '
        f'[ "$(/bin/busybox md5sum {TARGET_REMOTE_DIR}/usbg_video.v43.ko | /bin/busybox cut -d " " -f 1)" = "{EXPECTED_HASHES["usbg_video.v43.ko"]}" ]'
    )
    run_command(raw, verify_cmd, "STAGE_VERIFIED")
    print("[+] Staging verified successfully.")

    # Check im.elf maps for cold-boot requirement
    pid_out = run_command(raw, "/bin/busybox pidof im.elf", "PID_DONE")
    pid_match = re.search(r"(\d+)", pid_out)
    if not pid_match:
        raise RuntimeError("im.elf process not running!")
    pid = pid_match.group(1)

    raw.writeTerminal(f"/bin/busybox grep -q -E 'libInfraStreamingUsb|yuy2_' /proc/{pid}/maps; echo MAPS_RC $?\n".encode("ascii"))
    maps_log = pump_terminal(raw, seconds=5.0, marker="MAPS_RC")
    m_match = re.search(r"^MAPS_RC ([0-9]+)\r?$", maps_log, re.M)
    if m_match and m_match.group(1) == "0":
        print("[!] Streaming libraries currently mapped in im.elf. Cold reboot required.")
        print("[*] Triggering cold reboot (/bin/busybox sync; /bin/busybox reboot -f)...")
        raw.writeTerminal(b"/bin/busybox sync; /bin/busybox reboot -f\n")
        time.sleep(1.0)
        print("Camera reboot triggered. Re-run deploy script once camera reboots.")
        return

    print("[+] Cold-boot state clean: no streaming libraries mapped in im.elf.")

    # Execute install.sh
    print("[*] Running /bin/busybox sh /log/yuy2_1080_v43chunk/install.sh...")
    install_out = run_command(raw, f"/bin/busybox sh {TARGET_REMOTE_DIR}/install.sh", "INSTALL_SCRIPT_DONE", timeout=60.0)
    (DEPLOY_DIR / "install.log").write_text(install_out, encoding="latin1")
    if "V43_PATCH_INSTALLED_CONFIG_UNCHANGED" not in install_out:
        raise RuntimeError(f"install.sh did not return success marker.\nOutput:\n{install_out}")
    print("[+] install.sh reported: V43_PATCH_INSTALLED_CONFIG_UNCHANGED")

    # Read back files over USB
    print("[*] Reading back files from camera for byte-for-byte verification...")
    readbacks = [
        ("/usr/lib/yuy2_1080_v43chunk.so", READBACK_DIR / "yuy2_1080_v43chunk.so", EXPECTED_HASHES["yuy2_1080_v43chunk.so"]),
        ("/usr/lib/libInfraStreamingUsb.so", READBACK_DIR / "libInfraStreamingUsb.so", EXPECTED_HASHES["libInfraStreamingUsb.v43.so"]),
        ("/usr/kmod/usbg_video.ko", READBACK_DIR / "usbg_video.ko", EXPECTED_HASHES["usbg_video.v43.ko"]),
        ("/setting/DmmConfig.bin", READBACK_DIR / "DmmConfig.bin", EXPECTED_HASHES["DmmConfig.bin"]),
    ]

    verified_readbacks = {}
    for remote_path, local_path, expected_md5 in readbacks:
        buf = io.BytesIO()
        dev.readFile(remote_path, buf)
        data = buf.getvalue()
        local_path.write_bytes(data)
        actual_md5 = hashlib.md5(data).hexdigest()
        print(f"  {remote_path}: {len(data)} bytes, MD5 {actual_md5}")
        if actual_md5 != expected_md5:
            raise RuntimeError(f"Readback hash mismatch on {remote_path}! Got {actual_md5}, expected {expected_md5}")
        verified_readbacks[remote_path] = {"bytes": len(data), "md5": actual_md5, "verified": True}

    print("[+] All readback hashes match candidate binaries perfectly!")

    summary_file = DEPLOY_DIR / "deployment-summary.json"
    summary_data = {
        "status": "V43_INSTALLED_AND_VERIFIED",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "revision": "4.3-1080p-usb3-24fps-candidate",
        "dmm_config_untouched": True,
        "dmm_config_md5": EXPECTED_HASHES["DmmConfig.bin"],
        "files_installed": verified_readbacks,
    }
    summary_file.write_text(json.dumps(summary_data, indent=2) + "\n")
    print(f"\n[+] Deployment successfully completed! Summary written to {summary_file}")

    try:
        dev.setTerminalEnable(False)
    except Exception:
        pass


def main():
    print("=== Deploying Revision 4.3 (1080p YUY2 @ >=24fps) to Sony ZV-E10 ===")
    senserShellCommand(complete=deploy_session)
    return 0


if __name__ == "__main__":
    sys.exit(main())
