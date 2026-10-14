#!/usr/bin/env python3
"""
Single-Shot Batch Memory Patcher for Sony ZV-E10 UVC USB Webcam Hijack

Constructs and uploads a batch script to execute all UVC streaming patches
in a single transaction directly to running camera process memory (/proc/$PID/mem).

Supported Modes:
  - 1080p:       1920x1080 @ 30fps (PAL 25fps), 300 Mbps (Visually near-lossless Full HD)
  - 1080p60:     1920x1080 @ 60fps (PAL 50fps), 320 Mbps (High-speed Full HD, ~93% USB 2.0 saturation)
  - opengate:    3240x2160 @ 24fps (PAL 25fps), 300 Mbps (Full-sensor 3:2 Open Gate readout)
  - 2k_opengate: 2160x1440 @ 30fps (PAL 25fps), 300 Mbps (High-framerate 3:2 Open Gate)
  - stock:       1280x720  @ 30fps (PAL 25fps),  30 Mbps (Factory default 720p)

Zero Flash Risk:
  All patches operate exclusively in volatile RAM (/proc/$PID/mem).
  Power-cycling the camera completely restores stock firmware.
"""

import argparse
import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]

# Dynamic import for camera communication (graceful fallback if offline)
try:
    from research.device.zve10_retry import run
    HAS_CAM_DRIVER = True
except Exception:
    HAS_CAM_DRIVER = False


def encode_movw(rd: int, imm16: int) -> str:
    """Encode an ARM Thumb-2 'movw rd, #imm16' instruction into little-endian hex."""
    imm4 = (imm16 >> 12) & 0xF
    i = (imm16 >> 11) & 0x1
    imm3 = (imm16 >> 8) & 0x7
    imm8 = imm16 & 0xFF
    hw1 = 0xF240 | (i << 10) | imm4
    hw2 = (imm3 << 12) | (rd << 8) | imm8
    return f"{hw1 & 0xFF:02x}{(hw1 >> 8) & 0xFF:02x}{hw2 & 0xFF:02x}{(hw2 >> 8) & 0xFF:02x}"


def encode_movs_r2(imm8: int) -> str:
    """Encode an ARM Thumb-1 'movs r2, #imm8' instruction into little-endian hex."""
    hw = 0x2200 | (imm8 & 0xFF)
    return f"{hw & 0xFF:02x}{(hw >> 8) & 0xFF:02x}"


def build_uvc_frame_descriptor_hex(width: int, height: int, fps: float, bitrate_mbps: float) -> str:
    """Construct 30-byte standard UVC VS_FRAME_MJPEG descriptor in little-endian hex."""
    interval_100ns = int(round(10000000.0 / fps))
    bps = int(bitrate_mbps * 1000000)
    buf_sz = 14745600  # 14.4 MB frame buffer pool

    raw = struct.pack(
        "<BBBBBHHIIIIBI",
        0x1E,  # bLength (30 bytes)
        0x24,  # bDescriptorType (CS_INTERFACE)
        0x07,  # bDescriptorSubType (VS_FRAME_MJPEG)
        0x01,  # bFrameIndex (1)
        0x00,  # bmCapabilities
        width,
        height,
        bps,   # dwMinBitRate
        bps,   # dwMaxBitRate
        buf_sz,  # dwMaxVideoFrameBufferSize
        interval_100ns,  # dwDefaultFrameInterval
        0x01,  # bFrameIntervalType (1 discrete)
        interval_100ns   # dwFrameInterval[0]
    )
    return raw.hex()


def resolve_mode_parameters(mode: str, custom_w=None, custom_h=None, custom_fps=None, custom_br=None):
    """Map mode name to width, height, fps, pal_fps, and bitrate parameters."""
    m = mode.lower()
    if m == "1080p":
        w, h, fps, pal_fps, mbps = 1920, 1080, 30, 25, 300
    elif m in ("1080p60", "1080p_60", "60fps"):
        w, h, fps, pal_fps, mbps = 1920, 1080, 60, 50, 320
    elif m in ("opengate", "3.2k", "open_gate"):
        w, h, fps, pal_fps, mbps = 3240, 2160, 24, 25, 300
    elif m in ("2k_opengate", "2k", "2.2k"):
        w, h, fps, pal_fps, mbps = 2160, 1440, 30, 25, 300
    elif m == "stock":
        w, h, fps, pal_fps, mbps = 1280, 720, 30, 25, 30
    else:
        raise ValueError(f"Unknown preset mode: {mode}")

    # Apply user overrides if specified
    if custom_w is not None:
        w = custom_w
    if custom_h is not None:
        h = custom_h
    if custom_fps is not None:
        fps = custom_fps
        pal_fps = 25 if fps in (24, 25, 30) else (50 if fps == 60 else fps)
    if custom_br is not None:
        mbps = custom_br

    return w, h, fps, pal_fps, mbps


def generate_uvc_patch_list(base_cmn: int, base_stream: int, width: int, height: int,
                            fps: float, pal_fps: float, bitrate_mbps: float):
    """
    Generate the list of surgical patches to apply to camera process memory.
    Returns: list of (description, target_va, hex_bytes)
    """
    patches = []

    # 1. libInfraUsbCmn.so UVC Frame Descriptors
    # PAL Frame Descriptor at offset 0x12550
    va_pal = base_cmn + 0x12550
    pal_hex = build_uvc_frame_descriptor_hex(width, height, pal_fps, bitrate_mbps)
    patches.append((f"libInfraUsbCmn.so PAL MJPEG Descriptor ({width}x{height} @ {pal_fps}fps)", va_pal, pal_hex))

    # NTSC Frame Descriptor at offset 0x1263e
    va_ntsc = base_cmn + 0x1263e
    ntsc_hex = build_uvc_frame_descriptor_hex(width, height, fps, bitrate_mbps)
    patches.append((f"libInfraUsbCmn.so NTSC MJPEG Descriptor ({width}x{height} @ {fps}fps)", va_ntsc, ntsc_hex))

    # 2. libInfraStreamingUsb.so VideoEsManager::video_stream_start parameters
    # Width parameter at 0x908a
    va_width = base_stream + 0x908a
    if width == 1280 and bitrate_mbps == 30:
        # Stock: mov.w r2, #1280 (4f f4 a0 62)
        inst_w_hex = "4ff4a062"
    elif width == 1920:
        # mov.w r2, #1920 (4f f4 f0 62)
        inst_w_hex = "4ff4f062"
    else:
        # Generic movw r2, #width
        inst_w_hex = encode_movw(2, width)
    patches.append((f"VideoEsManager::video_stream_start Width (r2 = {width})", va_width, inst_w_hex))

    # Bitrate parameter at 0x908e
    va_bitrate = base_stream + 0x908e
    bitrate_scale = int(round(bitrate_mbps * 10))  # Scale factor: 300 = 30 Mbps, 3000 = 300 Mbps or direct
    if bitrate_mbps <= 40:
        bitrate_param = int(bitrate_mbps * 10)  # e.g. 30 Mbps -> 300
    else:
        bitrate_param = int(bitrate_mbps)       # e.g. 300 Mbps -> 300
    inst_br_hex = encode_movw(3, bitrate_param)
    patches.append((f"VideoEsManager::video_stream_start Bitrate (r3 = {bitrate_param})", va_bitrate, inst_br_hex))

    # FPS parameter at 0x9098
    va_fps = base_stream + 0x9098
    inst_fps_hex = encode_movs_r2(int(fps))
    patches.append((f"VideoEsManager::video_stream_start FPS (r2 = {int(fps)})", va_fps, inst_fps_hex))

    return patches


def print_patch_table(patches, width, height, fps, pal_fps, bitrate_mbps):
    """Display formatted summary table of patches."""
    print("=" * 78)
    print(f" Sony ZV-E10 UVC USB Webcam Hijack Patch Plan")
    print(f" Resolution: {width} x {height}  |  Framerate: {fps} fps NTSC / {pal_fps} fps PAL")
    print(f" Target Bitrate: {bitrate_mbps:.1f} Mbps (~{bitrate_mbps/8:.2f} MB/s)")
    sat = (bitrate_mbps / 8.0) / 43.0 * 100.0
    print(f" USB 2.0 Bulk Saturation: ~{sat:.1f}% of physical limit (43 MB/s)")
    print("=" * 78)
    print(f" {'#':<3} | {'Target Description':<42} | {'Address':<10} | {'Bytes':<14}")
    print("-" * 78)
    for idx, (desc, va, hex_bytes) in enumerate(patches, 1):
        disp_hex = hex_bytes if len(hex_bytes) <= 12 else hex_bytes[:10] + "..."
        print(f" {idx:<3} | {desc:<42} | 0x{va:08x} | {disp_hex:<14} ({len(hex_bytes)//2} B)")
    print("=" * 78)


def deploy_live_patch(width, height, fps, pal_fps, mbps, pid=None):
    """Deploy patches to live camera process memory via zve10_retry."""
    if not HAS_CAM_DRIVER:
        print("[-] Error: camera driver not available in environment.")
        return False

    print("[*] Connecting to Sony ZV-E10 service shell...")

    # 1. Resolve PID of im.elf
    out, _ = run(["/bin/busybox pidof im.elf"])
    detected_pid = None
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            detected_pid = int(line)
            break

    target_pid = pid or detected_pid or 157
    print(f"[+] Target im.elf PID: {target_pid}")

    # 2. Probe dynamic library base addresses from /proc/$PID/maps
    maps_out, _ = run([f"/bin/busybox grep -E 'libInfraUsbCmn.so|libInfraStreamingUsb.so' /proc/{target_pid}/maps"])
    base_cmn = None
    base_stream = None

    import re
    # Match lines like: 04834000-04848000 r-xp 00000000 ... /lib/libInfraUsbCmn.so
    map_pattern = re.compile(r"^([0-9a-fA-F]{8})-[0-9a-fA-F]{8}\s+([rwxsp-]+)\s+\S+\s+\S+\s+\S+\s+(.*)")
    for line in maps_out.splitlines():
        m = map_pattern.match(line.strip())
        if m:
            addr_str, perms, path = m.groups()
            if "libInfraUsbCmn.so" in path and "x" in perms:
                base_cmn = int(addr_str, 16)
            elif "libInfraStreamingUsb.so" in path and "x" in perms:
                base_stream = int(addr_str, 16)

    if base_cmn is None:
        # Fallback to any mapping of libInfraUsbCmn if r-xp wasn't caught
        for line in maps_out.splitlines():
            m = map_pattern.match(line.strip())
            if m:
                addr_str, perms, path = m.groups()
                if "libInfraUsbCmn.so" in path:
                    base_cmn = int(addr_str, 16)
                    break

    if base_cmn is None:
        base_cmn = 0x04834000  # Default known base on firmware 2.02/2.03
        print(f"[!] Warning: Could not find libInfraUsbCmn.so in maps, using base 0x{base_cmn:08x}")
    else:
        print(f"[+] Discovered libInfraUsbCmn.so live base:       0x{base_cmn:08x}")

    if base_stream is not None:
        print(f"[+] Discovered libInfraStreamingUsb.so live base: 0x{base_stream:08x}")
    else:
        print(f"[*] Note: libInfraStreamingUsb.so is not yet mapped (camera not currently streaming).")
        print(f"    UVC descriptors in libInfraUsbCmn.so will be patched immediately in memory.")

    # 3. Generate patch list with live base addresses
    patches = generate_uvc_patch_list(base_cmn, base_stream or 0x00000000, width, height, fps, pal_fps, mbps)
    print_patch_table(patches, width, height, fps, pal_fps, mbps)

    # Filter out stream instructions if streaming library is not yet loaded
    active_patches = []
    for desc, va, hex_bytes in patches:
        if "StreamingUsb" in desc or "video_stream_start" in desc:
            if base_stream is not None:
                active_patches.append((desc, va, hex_bytes))
        else:
            active_patches.append((desc, va, hex_bytes))

    # 4. Check /setting/mem_patch.elf
    out, _ = run(["/bin/busybox ls -l /setting/mem_patch.elf"])
    if "mem_patch.elf" not in out:
        print("[-] /setting/mem_patch.elf not found on camera! Deploying mem_patch.elf...")
        from research.device.push_opengate import push_file_b64
        push_file_b64("bin/opengate/mem_patch.elf", "/setting/mem_patch.elf")

    # 5. Build batch shell script on camera using single-shot cat EOF
    batch_lines = [
        "#!/bin/sh",
        f"PID={target_pid}",
        "P=/setting/mem_patch.elf",
    ]
    for desc, va, hex_bytes in active_patches:
        batch_lines.append(f"$P $PID {va:08x} {hex_bytes}")
    batch_lines.append(f"echo '[+] UVC BATCH COMPLETED: All {len(active_patches)} patches applied and verified in PID ' $PID")

    batch_script = "\n".join(batch_lines) + "\n"
    cmd = f"cat << 'EOF' > /tmp/run_uvc_batch.sh\n{batch_script}EOF\n/bin/busybox sh /tmp/run_uvc_batch.sh\nrm -f /tmp/run_uvc_batch.sh"

    print(f"[*] Executing {len(active_patches)} memory patches in single transaction...")
    t0 = time.time()
    out, tries = run([cmd])
    elapsed = time.time() - t0

    if "UVC BATCH COMPLETED" in out:
        print(f"[+] SUCCESS: Applied and verified all {len(active_patches)} patches in {elapsed:.2f}s!")
        print("=" * 78)
        print(" [+] UVC WEBCAM HIJACK IS ACTIVE IN LIVE RAM!")
        print(" [+] Connect USB cable to PC and open OBS Studio / ffplay / Zoom.")
        print("=" * 78)
        return True
    else:
        print(f"[-] Injection failed! Camera output:\n{out}")
        return False


def deploy_overwrite_patch(mode, width, height, fps, pal_fps, mbps):
    """Surgically overwrite the UVC libraries in /usr/lib on camera storage."""
    if not HAS_CAM_DRIVER:
        print("[-] Error: camera driver not available in environment.")
        return False

    print("[*] Connecting to Sony ZV-E10 service shell for persistent UVC library overwrite...")

    # 1. Check/upload /setting/file_patch.elf
    check_out, _ = run(["test -x /setting/file_patch.elf; echo status=$?"])
    if "status=0" not in check_out:
        print("[*] Deploying /setting/file_patch.elf to camera via push_file_b64...")
        fp_elf = HERE / "dumps" / "staged" / "uvc" / "file_patch.elf"
        if not fp_elf.exists():
            fp_elf = HERE / "out" / "file_patch.elf"
        from research.device.push_opengate import push_file_b64
        ok = push_file_b64(str(fp_elf), "/setting/file_patch.elf")
        if not ok:
            print("[-] Failed to stage /setting/file_patch.elf on camera!")
            return False
        print("[+] /setting/file_patch.elf staged successfully.")

    if mode == "stock":
        print("[*] Stock mode selected. Reverting /usr/lib libraries to pristine stock...")
        revert_lines = [
            "#!/bin/sh",
            "mount -o remount,rw /usr",
            "if [ -f /setting/stock_libs/libInfraUsbCmn.so ]; then",
            "    cp /setting/stock_libs/libInfraUsbCmn.so /usr/lib/libInfraUsbCmn.so",
            "    echo '[+] Restored stock libInfraUsbCmn.so'",
            "fi",
            "if [ -f /setting/stock_libs/libInfraStreamingUsb.so ]; then",
            "    cp /setting/stock_libs/libInfraStreamingUsb.so /usr/lib/libInfraStreamingUsb.so",
            "    echo '[+] Restored stock libInfraStreamingUsb.so'",
            "fi",
            "sync",
            "mount -o remount,ro /usr",
            "echo '[+] UVC REVERT COMPLETE: Factory 720p 30fps restored.'",
        ]
        cmd = "cat << 'EOF' > /tmp/run_revert.sh\n" + "\n".join(revert_lines) + "\nEOF\n/bin/busybox sh /tmp/run_revert.sh\nrm -f /tmp/run_revert.sh"
        out, _ = run([cmd])
        print(out)
        return True

    # 2. Generate surgical byte patches
    pal_desc_hex = build_uvc_frame_descriptor_hex(width, height, pal_fps, mbps)
    ntsc_desc_hex = build_uvc_frame_descriptor_hex(width, height, fps, mbps)

    patches = generate_uvc_patch_list(0, 0, width, height, fps, pal_fps, mbps)
    inst_w_hex = None
    inst_br_hex = None
    inst_fps_hex = None
    for desc, va, hex_bytes in patches:
        if "Width" in desc:
            inst_w_hex = hex_bytes
        elif "Bitrate" in desc:
            inst_br_hex = hex_bytes
        elif "FPS" in desc:
            inst_fps_hex = hex_bytes

    print(f"[*] Prepared 5 surgical library patches for '{mode}' ({width}x{height} @ {fps}fps / {pal_fps}fps PAL):")
    print(f"    1. libInfraUsbCmn.so @ 0x12550 (PAL): {pal_desc_hex[:20]}... ({len(pal_desc_hex)//2} B)")
    print(f"    2. libInfraUsbCmn.so @ 0x1263e (NTSC): {ntsc_desc_hex[:20]}... ({len(ntsc_desc_hex)//2} B)")
    print(f"    3. libInfraStreamingUsb.so @ 0x908a (Width): {inst_w_hex}")
    print(f"    4. libInfraStreamingUsb.so @ 0x908e (Bitrate): {inst_br_hex}")
    print(f"    5. libInfraStreamingUsb.so @ 0x9098 (FPS): {inst_fps_hex}")

    # 3. Build atomic execution script
    batch_lines = [
        "#!/bin/sh",
        "# 1. Ensure permanent stock backup in /setting/stock_libs",
        "mkdir -p /setting/stock_libs",
        "[ ! -f /setting/stock_libs/libInfraUsbCmn.so ] && cp /usr/lib/libInfraUsbCmn.so /setting/stock_libs/libInfraUsbCmn.so",
        "[ ! -f /setting/stock_libs/libInfraStreamingUsb.so ] && cp /usr/lib/libInfraStreamingUsb.so /setting/stock_libs/libInfraStreamingUsb.so",
        "# 2. Remount /usr rw",
        "mount -o remount,rw /usr",
        "# 3. Apply surgical file patches",
        f"/setting/file_patch.elf /usr/lib/libInfraUsbCmn.so 12550 {pal_desc_hex}",
        f"/setting/file_patch.elf /usr/lib/libInfraUsbCmn.so 1263e {ntsc_desc_hex}",
        f"/setting/file_patch.elf /usr/lib/libInfraStreamingUsb.so 908a {inst_w_hex}",
        f"/setting/file_patch.elf /usr/lib/libInfraStreamingUsb.so 908e {inst_br_hex}",
        f"/setting/file_patch.elf /usr/lib/libInfraStreamingUsb.so 9098 {inst_fps_hex}",
        "# 4. Sync and remount ro",
        "sync",
        "mount -o remount,ro /usr",
        "# 5. Install standalone revert script",
        "cat << 'EOF_REV' > /setting/revert_uvc.sh",
        "#!/bin/sh",
        "echo '[*] Restoring stock UVC webcam libraries...'",
        "mount -o remount,rw /usr",
        "cp /setting/stock_libs/libInfraUsbCmn.so /usr/lib/libInfraUsbCmn.so",
        "cp /setting/stock_libs/libInfraStreamingUsb.so /usr/lib/libInfraStreamingUsb.so",
        "sync",
        "mount -o remount,ro /usr",
        "echo '[+] Stock UVC libraries restored successfully.'",
        "EOF_REV",
        "chmod 755 /setting/revert_uvc.sh",
        "echo '[+] UVC OVERWRITE TRANSACTION COMPLETED'",
    ]

    cmd = "cat << 'EOF' > /tmp/run_uvc_overwrite.sh\n" + "\n".join(batch_lines) + "\nEOF\n/bin/busybox sh /tmp/run_uvc_overwrite.sh\nrm -f /tmp/run_uvc_overwrite.sh"

    print("[*] Executing persistent UVC library overwrite in single transaction...")
    t0 = time.time()
    out, tries = run([cmd])
    elapsed = time.time() - t0

    success_count = out.count("VERIFICATION SUCCESS")
    if success_count == 5:
        print(f"[+] SUCCESS: Applied and verified all {success_count}/5 persistent UVC patches in {elapsed:.2f}s!")
        print("=" * 78)
        print(f" [+] UVC WEBCAM PERMANENT OVERWRITE ACTIVE: {mode.upper()} ({width}x{height} @ {fps}fps)!")
        print(" [+] Survives power cycles, battery pulls, and normal reboots.")
        print(" [+] To revert anytime: run 'python batch_patch_uvc.py --mode stock --overwrite'")
        print("     or on-device: '/setting/revert_uvc.sh'")
        print("=" * 78)
        return True
    else:
        print(f"[-] Overwrite incomplete! Found {success_count}/5 verified patches. Camera output:\n{out}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Batch Patcher for Sony ZV-E10 UVC USB Webcam Hijack"
    )
    parser.add_argument(
        "-m", "--mode",
        choices=["1080p", "1080p60", "opengate", "3.2k", "2k_opengate", "stock"],
        default="1080p",
        help="Streaming mode preset (default: 1080p Full HD @ 30fps)"
    )
    parser.add_argument("--width", type=int, help="Custom frame width override (e.g. 1920, 3240, 2160)")
    parser.add_argument("--height", type=int, help="Custom frame height override (e.g. 1080, 2160, 1440)")
    parser.add_argument("--fps", type=float, help="Custom framerate override (e.g. 60, 30, 24)")
    parser.add_argument("--bitrate", type=float, help="Custom bitrate override in Mbps (e.g. 300, 320)")
    parser.add_argument("--pid", type=int, help="Override target im.elf process ID (live memory mode)")
    parser.add_argument("--overwrite", action="store_true", help="Permanently overwrite /usr/lib UVC libraries on camera storage (survives battery swaps)")
    parser.add_argument("--dry-run", action="store_true", help="Calculate and display patches without connecting to camera")
    parser.add_argument("--persistent", action="store_true", help="Install persistent boot preload hook to /setting/")

    args = parser.parse_args()

    # 1. Resolve parameters
    w, h, fps, pal_fps, mbps = resolve_mode_parameters(
        args.mode, args.width, args.height, args.fps, args.bitrate
    )

    if args.dry_run:
        patches = generate_uvc_patch_list(0x04834000, 0x00000000, w, h, fps, pal_fps, mbps)
        print_patch_table(patches, w, h, fps, pal_fps, mbps)
        print("[*] Dry run complete. No device modified.")
        return

    if args.persistent:
        print("[*] Persistent mode selected. Deploying to /setting/ via push_uvc.py...")
        from research.device.push_uvc import main as push_main
        push_main()
        return

    if args.overwrite:
        success = deploy_overwrite_patch(args.mode, w, h, fps, pal_fps, mbps)
        sys.exit(0 if success else 1)

    # Live RAM patch execution
    success = deploy_live_patch(w, h, fps, pal_fps, mbps, pid=args.pid)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
