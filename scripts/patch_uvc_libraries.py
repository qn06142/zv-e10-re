#!/usr/bin/env python3
"""
Generate Pre-Patched UVC Webcam Shared Libraries for Sony ZV-E10
Surgically patches dumps/camera_2025/usr/usr/lib/libInfraUsbCmn.so and libInfraStreamingUsb.so
for all modes: 1080p, 1080p60, opengate (3.2K), 2k_opengate, stock.
"""

import hashlib
import os
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path[:0] = [str(REPO_ROOT)]

import batch_patch_uvc as bpu

STOCK_CMN_PATH = REPO_ROOT / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libInfraUsbCmn.so"
STOCK_STREAM_PATH = REPO_ROOT / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libInfraStreamingUsb.so"
OUT_BASE = REPO_ROOT / "dumps" / "staged" / "uvc" / "binaries"

# Modes configuration
MODES = {
    "1080p": (1920, 1080, 30, 25, 300),
    "1080p60": (1920, 1080, 60, 50, 320),
    "opengate": (3240, 2160, 24, 25, 300),
    "2k_opengate": (2160, 1440, 30, 25, 300),
    "stock": (1280, 720, 30, 25, 30),
}


def patch_libraries(mode: str, width: int, height: int, fps: float, pal_fps: float, mbps: float):
    stock_cmn = STOCK_CMN_PATH.read_bytes()
    stock_stream = STOCK_STREAM_PATH.read_bytes()

    cmn_patched = bytearray(stock_cmn)
    stream_patched = bytearray(stock_stream)

    # 1. Patch libInfraUsbCmn.so descriptors
    pal_desc_hex = bpu.build_uvc_frame_descriptor_hex(width, height, pal_fps, mbps)
    ntsc_desc_hex = bpu.build_uvc_frame_descriptor_hex(width, height, fps, mbps)
    pal_desc_bytes = bytes.fromhex(pal_desc_hex)
    ntsc_desc_bytes = bytes.fromhex(ntsc_desc_hex)

    assert len(pal_desc_bytes) == 30
    assert len(ntsc_desc_bytes) == 30

    cmn_patched[0x12550 : 0x12550 + 30] = pal_desc_bytes
    cmn_patched[0x1263E : 0x1263E + 30] = ntsc_desc_bytes

    # 2. Patch libInfraStreamingUsb.so instructions
    patches = bpu.generate_uvc_patch_list(0, 0, width, height, fps, pal_fps, mbps)
    inst_width_hex = None
    inst_bitrate_hex = None
    inst_fps_hex = None

    for desc, va, hex_bytes in patches:
        if "Width" in desc:
            inst_width_hex = hex_bytes
        elif "Bitrate" in desc:
            inst_bitrate_hex = hex_bytes
        elif "FPS" in desc:
            inst_fps_hex = hex_bytes

    inst_width_bytes = bytes.fromhex(inst_width_hex)
    inst_bitrate_bytes = bytes.fromhex(inst_bitrate_hex)
    inst_fps_bytes = bytes.fromhex(inst_fps_hex)

    assert len(inst_width_bytes) == 4
    assert len(inst_bitrate_bytes) == 4
    assert len(inst_fps_bytes) == 2

    stream_patched[0x908A : 0x908A + 4] = inst_width_bytes
    stream_patched[0x908E : 0x908E + 4] = inst_bitrate_bytes
    stream_patched[0x9098 : 0x9098 + 2] = inst_fps_bytes

    # Assert overall file lengths are strictly invariant
    assert len(cmn_patched) == len(stock_cmn) == 94612
    assert len(stream_patched) == len(stock_stream) == 52524

    return bytes(cmn_patched), bytes(stream_patched)


def main():
    print("=================================================================")
    print(" Sony ZV-E10 UVC Shared Library Binary Patcher")
    print("=================================================================")

    if not STOCK_CMN_PATH.exists() or not STOCK_STREAM_PATH.exists():
        print("[-] Error: Stock libraries not found in dumps/camera_2025/!")
        sys.exit(1)

    for mode, (w, h, fps, pal_fps, mbps) in MODES.items():
        mode_dir = OUT_BASE / mode
        mode_dir.mkdir(parents=True, exist_ok=True)

        cmn_data, stream_data = patch_libraries(mode, w, h, fps, pal_fps, mbps)

        out_cmn = mode_dir / "libInfraUsbCmn.so"
        out_stream = mode_dir / "libInfraStreamingUsb.so"

        out_cmn.write_bytes(cmn_data)
        out_stream.write_bytes(stream_data)

        md5_cmn = hashlib.md5(cmn_data).hexdigest()
        md5_stream = hashlib.md5(stream_data).hexdigest()

        print(f"[+] Mode '{mode}': {w}x{h} @ {fps}fps NTSC / {pal_fps}fps PAL, {mbps} Mbps")
        print(f"    -> libInfraUsbCmn.so:       MD5={md5_cmn} ({len(cmn_data)} B)")
        print(f"    -> libInfraStreamingUsb.so: MD5={md5_stream} ({len(stream_data)} B)")

    print("\n[+] All modes generated successfully in dumps/staged/uvc/binaries/!")


if __name__ == "__main__":
    main()
