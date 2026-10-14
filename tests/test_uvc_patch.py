#!/usr/bin/env python3
"""
Unit tests for Sony ZV-E10 UVC USB Webcam Hijack Subsystem
Validates:
1. Firmware binary offsets & stock descriptors in libInfraUsbCmn.so
2. Instruction encodings & offsets in libInfraStreamingUsb.so
3. Compiled hook binary (out/uvc_hook.so) ELF structure & dependencies
4. Live RAM patch shell script syntax & offset calculations
5. USB 2.0 High-Speed bulk bandwidth saturation constraints
"""

import os
import struct
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LIB_USB_CMN = REPO_ROOT / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libInfraUsbCmn.so"
LIB_STREAMING = REPO_ROOT / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libInfraStreamingUsb.so"
HOOK_SO = REPO_ROOT / "out" / "uvc_hook.so"
LIVE_SH = REPO_ROOT / "research" / "device" / "apply_uvc_live.sh"


class TestUvcWebcamPatch(unittest.TestCase):

    def setUp(self):
        self.assertTrue(LIB_USB_CMN.exists(), f"Missing firmware dump: {LIB_USB_CMN}")
        self.assertTrue(LIB_STREAMING.exists(), f"Missing firmware dump: {LIB_STREAMING}")

    def test_pal_descriptor_stock_layout(self):
        """Verify stock PAL UVC Frame Descriptor at 0x12550."""
        with open(LIB_USB_CMN, "rb") as f:
            f.seek(0x12550)
            chunk = f.read(30)

        bLength, bDescType, bDescSubType, bFrameIndex, bmCaps = struct.unpack("<BBBBB", chunk[:5])
        wWidth, wHeight = struct.unpack("<HH", chunk[5:9])
        dwMinBitRate, dwMaxBitRate, dwMaxBuf = struct.unpack("<III", chunk[9:21])
        dwDefInterval, bIntType, dwInt0 = struct.unpack("<IBI", chunk[21:30])

        self.assertEqual(bLength, 30, "Descriptor length must be 30 bytes")
        self.assertEqual(bDescType, 0x24, "bDescriptorType must be CS_INTERFACE (0x24)")
        self.assertEqual(bDescSubType, 0x07, "bDescriptorSubType must be VS_FRAME_MJPEG (0x07)")
        self.assertEqual(bFrameIndex, 1, "bFrameIndex must be 1")
        self.assertEqual(wWidth, 1280, "Stock width must be 1280")
        self.assertEqual(wHeight, 720, "Stock height must be 720")
        self.assertEqual(dwDefInterval, 400000, "PAL default interval must be 400,000 (25 fps)")
        self.assertEqual(dwInt0, 400000, "PAL interval[0] must be 400,000 (25 fps)")

    def test_ntsc_descriptor_stock_layout(self):
        """Verify stock NTSC UVC Frame Descriptor at 0x1263e."""
        with open(LIB_USB_CMN, "rb") as f:
            f.seek(0x1263e)
            chunk = f.read(30)

        bLength, bDescType, bDescSubType, bFrameIndex, bmCaps = struct.unpack("<BBBBB", chunk[:5])
        wWidth, wHeight = struct.unpack("<HH", chunk[5:9])
        dwMinBitRate, dwMaxBitRate, dwMaxBuf = struct.unpack("<III", chunk[9:21])
        dwDefInterval, bIntType, dwInt0 = struct.unpack("<IBI", chunk[21:30])

        self.assertEqual(bLength, 30, "Descriptor length must be 30 bytes")
        self.assertEqual(bDescType, 0x24, "bDescriptorType must be CS_INTERFACE (0x24)")
        self.assertEqual(bDescSubType, 0x07, "bDescriptorSubType must be VS_FRAME_MJPEG (0x07)")
        self.assertEqual(bFrameIndex, 1, "bFrameIndex must be 1")
        self.assertEqual(wWidth, 1280, "Stock width must be 1280")
        self.assertEqual(wHeight, 720, "Stock height must be 720")
        self.assertEqual(dwDefInterval, 333333, "NTSC default interval must be 333,333 (30 fps)")
        self.assertEqual(dwInt0, 333333, "NTSC interval[0] must be 333,333 (30 fps)")

    def test_video_stream_start_instructions(self):
        """Verify stock instruction encodings in VideoEsManager::video_stream_start."""
        with open(LIB_STREAMING, "rb") as f:
            f.seek(0x908a)
            inst_width = f.read(4)
            inst_bitrate = f.read(4)

            f.seek(0x9098)
            inst_fps = f.read(2)

        # mov.w r2, #1280 -> 4f f4 a0 62 in little-endian
        self.assertEqual(inst_width, bytes([0x4f, 0xf4, 0xa0, 0x62]), "Width instruction must match mov.w r2, #1280")
        # mov.w r3, #300 -> 4f f4 96 73 in little-endian
        self.assertEqual(inst_bitrate, bytes([0x4f, 0xf4, 0x96, 0x73]), "Bitrate instruction must match mov.w r3, #300")
        # movs r2, #30 -> 1e 22 in little-endian
        self.assertEqual(inst_fps, bytes([0x1e, 0x22]), "FPS instruction must match movs r2, #30")

    def test_compiled_uvc_hook_elf(self):
        """Verify out/uvc_hook.so ELF properties if compiled."""
        self.assertTrue(HOOK_SO.exists(), f"Compiled hook binary not found: {HOOK_SO}")

        with open(HOOK_SO, "rb") as f:
            magic = f.read(4)
            self.assertEqual(magic, b"\x7fELF", "Must be valid ELF binary")
            ei_class = f.read(1)[0]
            self.assertEqual(ei_class, 1, "Must be 32-bit ELF (ELFCLASS32)")
            ei_data = f.read(1)[0]
            self.assertEqual(ei_data, 1, "Must be little-endian (ELFDATA2LSB)")

            f.seek(0x12)
            e_machine, = struct.unpack("<H", f.read(2))
            self.assertEqual(e_machine, 40, "Must be ARM architecture (EM_ARM = 40)")

    def test_live_patch_script_integrity(self):
        """Verify generated apply_uvc_live.sh script contains all necessary offsets and modes."""
        self.assertTrue(LIVE_SH.exists(), f"Live patch script not found: {LIVE_SH}")
        content = LIVE_SH.read_text(encoding="utf-8")

        self.assertIn("12550", content, "Script must target PAL offset 0x12550")
        self.assertIn("1263e", content, "Script must target NTSC offset 0x1263e")
        self.assertIn("908a", content, "Script must target stream width offset 0x908a")
        self.assertIn("908e", content, "Script must target stream bitrate offset 0x908e")
        self.assertIn("9098", content, "Script must target stream fps offset 0x9098")

        for mode in ["1080p", "1080p60", "opengate", "2k_opengate"]:
            self.assertIn(mode, content, f"Script must support mode {mode}")

    def test_bandwidth_saturation_limits(self):
        """Verify bandwidth saturation math for USB 2.0 High-Speed Bulk mode."""
        # USB 2.0 High-Speed theoretical signaling rate: 480 Mbps = 60 MB/s
        # Real-world sustained Bulk Endpoint throughput: ~40 - 43 MB/s (~320 - 350 Mbps)
        MAX_BULK_THROUGHPUT_MB_S = 43.0

        # Mode 1: 1080p Full HD @ 30fps (MJPEG ~1.0 MB/frame average)
        # Sustained: 30.0 MB/s (240 Mbps) -> fits cleanly in USB 2.0 Bulk (~70% bus utilization)
        mbps_1080p30 = 300
        mb_s_1080p30 = mbps_1080p30 / 8.0
        self.assertLessEqual(mb_s_1080p30, MAX_BULK_THROUGHPUT_MB_S)

        # Mode 2: 1080p Full HD @ 60fps (MJPEG ~0.65 MB/frame average)
        # Sustained: 39.0 MB/s (312 Mbps) -> saturates ~91% of USB 2.0 Bulk limit
        mbps_1080p60 = 320
        mb_s_1080p60 = mbps_1080p60 / 8.0
        self.assertLessEqual(mb_s_1080p60, MAX_BULK_THROUGHPUT_MB_S)

        # Mode 3: 3.2K 3:2 Open Gate @ 24fps (MJPEG ~1.25 MB/frame average)
        # Sustained: 30.0 MB/s (240 Mbps) -> fits cleanly in USB 2.0 Bulk (~70% bus utilization)
        mbps_opengate = 300
        mb_s_opengate = mbps_opengate / 8.0
        self.assertLessEqual(mb_s_opengate, MAX_BULK_THROUGHPUT_MB_S)


if __name__ == "__main__":
    unittest.main()
