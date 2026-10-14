#!/usr/bin/env python3
"""
Generator for Sony ZV-E10 UVC Webcam Live RAM Patch Script (apply_uvc_live.sh)
Generates shell script that applies dynamic in-memory patches to im.elf via mem_patch.elf.
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
OUT_FILE = HERE / "research" / "device" / "apply_uvc_live.sh"

SCRIPT_CONTENT = """#!/bin/sh
# Sony ZV-E10 Live UVC Webcam Hijack Patch
# Applies volatile RAM patch directly to im.elf process via /setting/mem_patch.elf
# Usage: ./apply_uvc_live.sh [1080p | 1080p60 | opengate | 2k_opengate]

MODE="${1:-1080p}"

PID=$(pidof im.elf)
if [ -z "$PID" ]; then
    PID=157
    echo "[!] im.elf not found via pidof, falling back to default PID $PID"
fi

echo "=========================================================="
echo " Sony ZV-E10 UVC USB Webcam Live RAM Patch"
echo " Target im.elf PID: $PID"
echo " Selected Mode:     $MODE"
echo "=========================================================="

MAPS="/proc/$PID/maps"
if [ ! -f "$MAPS" ]; then
    echo "[-] Error: $MAPS not accessible"
    exit 1
fi

BASE_CMN_HEX=$(grep 'libInfraUsbCmn.so' "$MAPS" | head -n 1 | cut -d'-' -f1)
BASE_STREAM_HEX=$(grep 'libInfraStreamingUsb.so' "$MAPS" | head -n 1 | cut -d'-' -f1)

if [ -z "$BASE_CMN_HEX" ] || [ -z "$BASE_STREAM_HEX" ]; then
    echo "[-] Error: Failed to find target libraries in process memory maps!"
    exit 1
fi

echo "[+] libInfraUsbCmn.so base:       0x$BASE_CMN_HEX"
echo "[+] libInfraStreamingUsb.so base: 0x$BASE_STREAM_HEX"

# Convert hex base to decimal for offset arithmetic
BASE_CMN=$((0x$BASE_CMN_HEX))
BASE_STREAM=$((0x$BASE_STREAM_HEX))

# Target offsets
# libInfraUsbCmn.so:
# PAL descriptor:  0x12550
# NTSC descriptor: 0x1263e
VA_PAL_DEC=$((BASE_CMN + 0x12550))
VA_NTSC_DEC=$((BASE_CMN + 0x1263e))

# libInfraStreamingUsb.so:
# video_stream_start width instruction:   0x908a (4 bytes)
# video_stream_start bitrate instruction: 0x908e (4 bytes)
# video_stream_start fps instruction:     0x9098 (2 bytes)
VA_STREAM_W_DEC=$((BASE_STREAM + 0x908a))
VA_STREAM_BR_DEC=$((BASE_STREAM + 0x908e))
VA_STREAM_FPS_DEC=$((BASE_STREAM + 0x9098))

VA_PAL=$(printf "%08x" $VA_PAL_DEC)
VA_NTSC=$(printf "%08x" $VA_NTSC_DEC)
VA_STREAM_W=$(printf "%08x" $VA_STREAM_W_DEC)
VA_STREAM_BR=$(printf "%08x" $VA_STREAM_BR_DEC)
VA_STREAM_FPS=$(printf "%08x" $VA_STREAM_FPS_DEC)

case "$MODE" in
    1080p)
        echo "[*] Configuring 1080p Full HD (1920x1080 @ 30fps NTSC / 25fps PAL)..."
        # PAL: 1920x1080 @ 25fps (interval 400000 = 0x00061a80), bitrate 300 Mbps (0x11e1a300)
        # Bytes: 1e 24 07 01 00 80 07 38 04 00 a3 e1 11 00 a3 e1 11 00 e1 00 80 1a 06 00 01 80 1a 06 00
        PAL_HEX="1e240701008007380400a3e11100a3e11100e100801a060001801a0600"
        # NTSC: 1920x1080 @ 30fps (interval 333333 = 0x00051615), bitrate 300 Mbps (0x11e1a300)
        # Bytes: 1e 24 07 01 00 80 07 38 04 00 a3 e1 11 00 a3 e1 11 00 e1 00 15 16 05 00 01 15 16 05 00
        NTSC_HEX="1e240701008007380400a3e11100a3e11100e100151605000115160500"
        # mov.w r2, #1920 -> 4f f4 f0 62
        STREAM_W_HEX="f0624ff4"
        # mov.w r3, #300  -> 4f f4 96 73
        STREAM_BR_HEX="96734ff4"
        # movs r2, #30    -> 1e 22
        STREAM_FPS_HEX="1e22"
        ;;
    1080p60)
        echo "[*] Configuring 1080p Full HD (1920x1080 @ 60fps NTSC / 50fps PAL)..."
        # PAL: 1920x1080 @ 50fps (interval 200000 = 0x00030d40), bitrate 320 Mbps (0x1312d000)
        PAL_HEX="1e240701008007380400d0121300d0121300e100400d030001400d0300"
        # NTSC: 1920x1080 @ 60fps (interval 166666 = 0x00028baa), bitrate 320 Mbps (0x1312d000)
        NTSC_HEX="1e240701008007380400d0121300d0121300e100aa8b020001aa8b0200"
        # mov.w r2, #1920 -> 4f f4 f0 62
        STREAM_W_HEX="f0624ff4"
        # mov.w r3, #320 (0x140) -> 4f f4 a0 73
        STREAM_BR_HEX="a0734ff4"
        # movs r2, #60    -> 3c 22
        STREAM_FPS_HEX="3c22"
        ;;
    opengate|3.2k)
        echo "[*] Configuring 3.2K 3:2 Open Gate (3240x2160 @ 24fps)..."
        # PAL: 3240x2160 @ 25fps (interval 400000 = 0x00061a80)
        PAL_HEX="1e24070100a80c700800a3e11100a3e11100e100801a060001801a0600"
        # NTSC: 3240x2160 @ 24fps (interval 416666 = 0x00065c6a)
        NTSC_HEX="1e24070100a80c700800a3e11100a3e11100e1006a5c0600016a5c0600"
        # movw r2, #3240 (0x0ca8) -> 40 f6 a8 42
        STREAM_W_HEX="a84240f6"
        # mov.w r3, #300  -> 4f f4 96 73
        STREAM_BR_HEX="96734ff4"
        # movs r2, #24    -> 18 22
        STREAM_FPS_HEX="1822"
        ;;
    2k_opengate)
        echo "[*] Configuring 2.2K 3:2 Open Gate (2160x1440 @ 30fps)..."
        # PAL: 2160x1440 @ 25fps (interval 400000 = 0x00061a80)
        PAL_HEX="1e240701007008a00500a3e11100a3e11100e100801a060001801a0600"
        # NTSC: 2160x1440 @ 30fps (interval 333333 = 0x00051615)
        NTSC_HEX="1e240701007008a00500a3e11100a3e11100e100151605000115160500"
        # movw r2, #2160 (0x0870) -> 40 f6 70 02
        STREAM_W_HEX="700240f6"
        # mov.w r3, #300  -> 4f f4 96 73
        STREAM_BR_HEX="96734ff4"
        # movs r2, #30    -> 1e 22
        STREAM_FPS_HEX="1e22"
        ;;
    *)
        echo "[-] Unknown mode: $MODE (choose: 1080p, 1080p60, opengate, 2k_opengate)"
        exit 1
        ;;
esac

MEM_PATCH="/setting/mem_patch.elf"
if [ ! -x "$MEM_PATCH" ]; then
    echo "[-] Error: $MEM_PATCH executable not found or not executable!"
    exit 1
fi

echo "[*] 1. Patching PAL UVC Frame Descriptor at 0x$VA_PAL..."
$MEM_PATCH $PID $VA_PAL $PAL_HEX

echo "[*] 2. Patching NTSC UVC Frame Descriptor at 0x$VA_NTSC..."
$MEM_PATCH $PID $VA_NTSC $NTSC_HEX

echo "[*] 3. Patching VideoEsManager stream width at 0x$VA_STREAM_W..."
$MEM_PATCH $PID $VA_STREAM_W $STREAM_W_HEX

echo "[*] 4. Patching VideoEsManager stream bitrate at 0x$VA_STREAM_BR..."
$MEM_PATCH $PID $VA_STREAM_BR $STREAM_BR_HEX

echo "[*] 5. Patching VideoEsManager stream fps at 0x$VA_STREAM_FPS..."
$MEM_PATCH $PID $VA_STREAM_FPS $STREAM_FPS_HEX

echo "=========================================================="
echo " [+] UVC WEBCAM HIJACK LIVE PATCH APPLIED SUCCESSFULLY!"
echo " [+] Mode: $MODE"
echo " [+] Connect camera to PC and open OBS Studio / ffplay!"
echo "=========================================================="
"""


def main():
    print(f"[*] Generating {OUT_FILE}...")
    with open(OUT_FILE, "w", newline="\n") as f:
        f.write(SCRIPT_CONTENT)
    print(f"[+] Successfully generated {OUT_FILE}")


if __name__ == "__main__":
    main()
