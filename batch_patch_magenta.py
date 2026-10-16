#!/usr/bin/env python3
"""Batch patcher for Sony ZV-E10 Magenta Framing Lines Patch.

Recolours live-view framing guide lines on the LCD from stock grey to vibrant magenta.
Targets: /usr/share/app/color_cmn.uxc (312 bytes).
Offset: 0xbc (Entry 0x400c) -> [0xff, 0x00, 0xff, 0xff]
"""

import argparse
import sys
import base64
from pathlib import Path

STOCK_MD5 = "f468bd3e72ca4e5b948a1c9f1f35c0a1"
MAGENTA_MD5 = "c169428ea6ef0e924235164a0b33e528"
BLUE_MD5 = "9474c2846a1a952179a2408018ff0295"

HERE = Path(__file__).resolve().parent
STAGED_PALETTE = HERE / "dumps" / "staged" / "palette"

try:
    import research.device.zve10_retry as zve10
    HAS_CAM = True
except ImportError:
    HAS_CAM = False


def patch_file_bytes(raw_bytes: bytes, mode: str = "magenta") -> bytes:
    if len(raw_bytes) != 312:
        raise ValueError(f"Expected 312 bytes for color_cmn.uxc, got {len(raw_bytes)}")
    out = bytearray(raw_bytes)
    if mode == "magenta":
        # 0xbc: 33 33 33 80 -> ff 00 ff ff
        out[0xbc:0xc0] = b"\xff\x00\xff\xff"
    elif mode == "stock":
        out[0xbc:0xc0] = b"\x33\x33\x33\x80"
        # also restore 0xa5:0xa7 if blue build was applied
        out[0xa5:0xa7] = b"\x00\xdd"
    elif mode == "blue":
        out[0xa5:0xa7] = b"\xff\xff"
        out[0xbc:0xc0] = b"\x00\x00\xdd\x80"
    return bytes(out)


def deploy_to_camera(mode: str = "magenta", cold_reboot: bool = True):
    if not HAS_CAM:
        print("[-] Camera driver not available.")
        return False

    print(f"[*] Preparing {mode.upper()} palette patch for camera...")
    # Read reference binary or patch
    src_file = STAGED_PALETTE / f"color_cmn.{'MAGENTA_BUILD' if mode == 'magenta' else ('STOCK' if mode == 'stock' else 'BLUE_BUILD')}.uxc"
    if src_file.exists():
        data = src_file.read_bytes()
    else:
        stock_file = STAGED_PALETTE / "color_cmn.STOCK.uxc"
        if not stock_file.exists():
            print(f"[-] Reference palette file not found at {src_file}")
            return False
        data = patch_file_bytes(stock_file.read_bytes(), mode)

    b64_str = base64.b64encode(data).decode("ascii")
    expected_md5 = MAGENTA_MD5 if mode == "magenta" else (STOCK_MD5 if mode == "stock" else BLUE_MD5)

    cmds = [
        "mount -o remount,rw /usr",
        f"echo '{b64_str}' | /bin/busybox base64 -d > /usr/share/app/color_cmn.uxc",
        "sync",
        "/bin/busybox md5sum /usr/share/app/color_cmn.uxc",
        "mount -o remount,ro /usr",
        "sync",
    ]
    if cold_reboot:
        cmds.append("/bin/busybox reboot -f")

    print(f"[*] Deploying to /usr/share/app/color_cmn.uxc (Expected MD5: {expected_md5})...")
    out, attempts = zve10.run(cmds)
    print(out)

    if expected_md5 in out:
        print(f"[+] SUCCESS: Verified {mode.upper()} palette patch installed on camera!")
        if cold_reboot:
            print("[+] Camera is rebooting into shooting mode.")
        return True
    else:
        print("[-] Verification failed! MD5 did not match.")
        return False


def main():
    parser = argparse.ArgumentParser(description="Sony ZV-E10 Magenta Framing Lines Patch")
    parser.add_argument("--mode", choices=["magenta", "stock", "blue"], default="magenta",
                        help="Palette mode to apply (default: magenta)")
    parser.add_argument("--revert", action="store_true", help="Revert to factory stock palette")
    parser.add_argument("--no-reboot", action="store_true", help="Do not reboot camera after writing")
    parser.add_argument("--file", type=str, help="Patch a local color_cmn.uxc file instead of camera")
    args = parser.parse_args()

    mode = "stock" if args.revert else args.mode

    if args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"[-] File not found: {p}")
            sys.exit(1)
        patched = patch_file_bytes(p.read_bytes(), mode)
        p.write_bytes(patched)
        print(f"[+] Patched {p} to {mode.upper()} mode.")
        sys.exit(0)

    success = deploy_to_camera(mode, cold_reboot=not args.no_reboot)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
