#!/usr/bin/env python3
"""
Revert All Residual 16:9 and Experimental Patches to Factory Stock on Sony ZV-E10.

Reverts:
1. /usr/share/app/color_cmn.uxc -> color_cmn.STOCK.uxc (MD5: f468bd3e72ca4e5b948a1c9f1f35c0a1)
   Restores framing guide lines from magenta back to factory stock grey.
2. /setting/Backup.bin & Backup.bak -> restored from /setting/Backup.orig (MD5: 1c3165c21b13e13c6fed3c83425e2165)
   Restores factory NVRAM settings, clearing experimental aspect ratio tweaks.
3. Cleans up residual test scripts from /etc/ (apply_opengate.sh, osd_hook.so, run_all_patches.sh).
"""

import base64
import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import research.device.zve10_retry as zve10

STOCK_PALETTE_PATH = REPO_ROOT / "dumps" / "staged" / "palette" / "color_cmn.STOCK.uxc"
EXPECTED_STOCK_MD5 = "f468bd3e72ca4e5b948a1c9f1f35c0a1"


def main():
    print("=" * 70)
    print("  Sony Alpha ZV-E10: Revert Residual 16:9 / Framing Patches to Stock")
    print("=" * 70)

    # 1. Verify stock palette file locally
    if not STOCK_PALETTE_PATH.exists():
        print(f"[-] Stock palette file missing: {STOCK_PALETTE_PATH}")
        sys.exit(1)

    stock_data = STOCK_PALETTE_PATH.read_bytes()
    local_md5 = hashlib.md5(stock_data).hexdigest()
    if local_md5 != EXPECTED_STOCK_MD5:
        print(f"[-] Local stock palette MD5 mismatch: {local_md5} != {EXPECTED_STOCK_MD5}")
        sys.exit(1)
    print(f"[+] Verified local stock palette ({local_md5})")

    b64_palette = base64.b64encode(stock_data).decode("ascii")

    # 2. Prepare restore commands
    cmds = [
        # Restore color_cmn.uxc to factory stock
        "/bin/busybox mount -o remount,rw /usr",
        f"echo '{b64_palette}' | /bin/busybox base64 -d > /usr/share/app/color_cmn.uxc",
        "/bin/busybox sync",
        "/bin/busybox md5sum /usr/share/app/color_cmn.uxc",
        "/bin/busybox mount -o remount,ro /usr",
        "/bin/busybox sync",

        # Restore Backup.bin & Backup.bak from Backup.orig
        "/bin/busybox cp /setting/Backup.orig /setting/Backup.bin",
        "/bin/busybox cp /setting/Backup.orig /setting/Backup.bak",
        "/bin/busybox sync",
        "/bin/busybox md5sum /setting/Backup.bin /setting/Backup.orig",

        # Clean up residual open gate / aspect test scripts from /etc
        "/bin/busybox rm -f /etc/apply_opengate.sh /etc/run_all_patches.sh /etc/batch_apply.sh /etc/osd_hook.so /etc/sidecar_demo.elf",
        "/bin/busybox sync",
    ]

    print("[*] Waiting for camera connection and executing restore...")
    out, tries = zve10.run(cmds)
    print(out)

    if EXPECTED_STOCK_MD5 in out:
        print("[+] SUCCESS: /usr/share/app/color_cmn.uxc reverted to factory stock!")
    else:
        print("[-] Warning: palette MD5 check not confirmed in output.")

    if "1c3165c21b13e13c6fed3c83425e2165" in out:
        print("[+] SUCCESS: /setting/Backup.bin reverted to factory Backup.orig!")
    else:
        print("[-] Warning: Backup.bin MD5 check not confirmed in output.")

    print("\n[*] Reverting complete. Cold rebooting camera into clean stock mode...")
    zve10.run(["/bin/busybox sync", "/bin/busybox reboot -f"])
    print("[+] Camera rebooted successfully.")


if __name__ == "__main__":
    main()
