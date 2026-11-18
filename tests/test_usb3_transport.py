#!/usr/bin/env python3
"""
Unit and Integration Test Suite for USB 3.0 SuperSpeed UVC Transport and 24fps Continuous Pipeline.
"""

from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

from research.firmware.usb3_24fps_transport.verify_usb3_descriptors import (
    verify_kernel_dwc3,
    verify_usb_cmn_superspeed_tables,
    compute_bandwidth_budget,
)
from scripts.patch_uvc_usb3_24fps import PROFILES, build_vs_frame_descriptor
from tests.test_uvc_patch import LinuxUvcEmulator, WindowsUvcEmulator, MacOsUvcEmulator
from research.firmware.raw_frame_source.verified_bayer.live_bayer_tap_v01.verify_bayer_tap import (
    check_frame_size_and_geometries,
    check_dma330_alignment_rules,
    check_ring_buffer_24fps_simulation,
)
from research.firmware.usb3_24fps_transport.host_usb3_receiver import HostUsb3Receiver


class TestUsb3SuperSpeedTransport(unittest.TestCase):
    """Test suite validating USB 3.0 SuperSpeed capabilities and bandwidth calculations."""

    def test_kernel_dwc3_superspeed_support(self):
        results = {}
        verify_kernel_dwc3(results)
        kinfo = results.get("kernel_dwc3_superspeed", {})
        self.assertEqual(kinfo.get("status"), "PASS")
        self.assertTrue(kinfo.get("dwc3_gadget_present"))
        self.assertTrue(kinfo.get("usb3_set_sel_present"))
        self.assertTrue(kinfo.get("usb3_u1_u2_power_states_present"))
        self.assertTrue(kinfo.get("otgcore_gadget_switch_present"))

    def test_libinfrasusbcmn_superspeed_descriptors(self):
        results = {}
        verify_usb_cmn_superspeed_tables(results)
        uinfo = results.get("libInfraUsbCmn_superspeed", {})
        self.assertEqual(uinfo.get("status"), "PASS")
        self.assertTrue(uinfo.get("speed_3_maps_to_cusb_speed_super"))
        self.assertEqual(uinfo.get("ep_address"), "0x81")
        self.assertEqual(uinfo.get("ep_attributes"), "0x2")
        self.assertEqual(uinfo.get("ep_wMaxPacketSize"), 1024)
        self.assertEqual(uinfo.get("vs_wTotalLength"), 61)

    def test_bandwidth_budget_24fps_feasibility(self):
        results = {}
        compute_bandwidth_budget(results)
        binfo = results.get("bandwidth_budget_24fps", {})
        self.assertEqual(binfo.get("status"), "PASS")
        modes = binfo.get("modes", [])
        self.assertGreaterEqual(len(modes), 5)
        for m in modes:
            self.assertTrue(m["fits_in_usb3"], f"Mode {m['mode']} exceeds USB 3 bandwidth")
            self.assertLess(m["bus_utilization_pct"], 75.0, f"Mode {m['mode']} has insufficient headroom")

    def test_patch_uvc_usb3_24fps_profiles(self):
        """Verify UVC descriptor hierarchy for all 24fps/30fps USB3 profiles against OS parsers."""
        repo_root = Path(__file__).resolve().parent.parent
        stock_cmn = repo_root / '.local/dumps' / "camera_2025" / "usr" / "usr" / "lib" / "libInfraUsbCmn.so"
        stock_data = bytearray(stock_cmn.read_bytes())

        for pname, profile in PROFILES.items():
            desc_bytes = build_vs_frame_descriptor(profile)
            self.assertEqual(len(desc_bytes), 30)

            # Inject into NTSC slot at 0x1263E
            test_buf = bytearray(stock_data)
            test_buf[0x1263E:0x1263E + 30] = desc_bytes

            # Validate against Linux, Windows, macOS emulators
            l_res = LinuxUvcEmulator.parse_streaming(bytes(test_buf), 0x12625)
            self.assertEqual(l_res["status"], "SUCCESS")

            w_res = WindowsUvcEmulator.validate_stream_descriptor(bytes(test_buf), 0x12625, endpoint_packet_size=512)
            self.assertEqual(w_res["status"], "SUCCESS")

            m_res = MacOsUvcEmulator.validate_stream_descriptor(bytes(test_buf), 0x12625)
            self.assertEqual(m_res["status"], "SUCCESS")

            parsed_frame = l_res["parsed"]["frames"][0]
            self.assertEqual(parsed_frame["wWidth"], profile.width)
            self.assertEqual(parsed_frame["wHeight"], profile.height)
            self.assertEqual(parsed_frame["dwDefaultFrameInterval"], profile.frame_interval_100ns)

    def test_bayer_tap_liveview_ring(self):
        """Validate live bayer tap geometry, alignment, and 100-frame ring simulation."""
        log = []
        check_frame_size_and_geometries(log)
        check_dma330_alignment_rules(log)
        check_ring_buffer_24fps_simulation(log)
        for item in log:
            self.assertEqual(item["status"], "PASS", f"Failed tap test: {item}")

    def test_host_receiver_mock_session(self):
        """Validate host spooler mock capture session execution and stats recording."""
        with tempfile.TemporaryDirectory() as tmpdir:
            receiver = HostUsb3Receiver(output_dir=Path(tmpdir), target_fps=24.0, expected_frame_size=2592000)
            stats = receiver.run_mock_session(num_frames=30)
            self.assertTrue(stats.success)
            self.assertEqual(stats.total_frames, 30)
            self.assertGreater(stats.actual_fps, 20.0)
            self.assertGreater(stats.average_throughput_mb_s, 50.0)
            frame0 = Path(tmpdir) / "frame_000000.raw"
            self.assertTrue(frame0.is_file())
            self.assertEqual(frame0.stat().st_size, 2592000)

    def test_host_receiver_1080p_yuy2_session(self):
        """Validate host spooler for 1080p YUY2 @ 24fps and 30fps with 4,147,200 B frame size."""
        from research.firmware.usb3_24fps_transport.host_usb3_receiver import FORMAT_PRESETS

        # Test 24 fps
        with tempfile.TemporaryDirectory() as tmpdir:
            receiver = HostUsb3Receiver(output_dir=Path(tmpdir), target_fps=24.0, preset="yuy2_1080p")
            self.assertEqual(receiver.width, 1920)
            self.assertEqual(receiver.height, 1080)
            self.assertEqual(receiver.expected_frame_size, 4147200)

            stats = receiver.run_mock_session(num_frames=24)
            self.assertTrue(stats.success)
            self.assertEqual(stats.total_frames, 24)
            self.assertEqual(stats.total_bytes, 4147200 * 24)
            self.assertEqual(stats.width, 1920)
            self.assertEqual(stats.height, 1080)

            # Spooled frames must have .yuy2 extension and exactly 4,147,200 bytes
            frame0 = Path(tmpdir) / "frame_000000.yuy2"
            self.assertTrue(frame0.is_file())
            self.assertEqual(frame0.stat().st_size, 4147200)

            # Check valid YUY2 neutral byte pattern
            data0 = frame0.read_bytes()
            self.assertEqual(data0[:4], b"\x10\x80\x10\x80")

        # Test 30 fps
        with tempfile.TemporaryDirectory() as tmpdir:
            receiver30 = HostUsb3Receiver(output_dir=Path(tmpdir), target_fps=30.0, preset="yuy2_1080p")
            stats30 = receiver30.run_mock_session(num_frames=30)
            self.assertTrue(stats30.success)
            self.assertEqual(stats30.total_frames, 30)
            self.assertEqual(stats30.total_bytes, 4147200 * 30)

    def test_host_receiver_format_presets(self):
        """Validate all supported format presets have consistent geometry and sizing."""
        from research.firmware.usb3_24fps_transport.host_usb3_receiver import FORMAT_PRESETS

        expected_presets = ["yuy2_1080p", "yuy2_720p", "yuy2_vga", "raw10_1080p", "raw12_1080p", "raw14_1080p"]
        for p in expected_presets:
            self.assertIn(p, FORMAT_PRESETS)
            cfg = FORMAT_PRESETS[p]
            computed_size = int(cfg["width"] * cfg["height"] * cfg["bytes_per_pixel"])
            self.assertEqual(cfg["frame_size"], computed_size)

        # 1080p YUY2 must strictly equal 4,147,200 bytes
        self.assertEqual(FORMAT_PRESETS["yuy2_1080p"]["frame_size"], 4147200)
        # VGA YUY2 must strictly equal 614,400 bytes (matches stock staging buffer)
        self.assertEqual(FORMAT_PRESETS["yuy2_vga"]["frame_size"], 614400)

    def test_1080p_yuy2_chunked_timing_on_usb3(self):
        """Validate 7-chunk 1080p YUY2 delivery timing over USB 3.0 SuperSpeed link."""
        frame_bytes = 1920 * 1080 * 2  # 4,147,200 bytes
        chunk_size = 614400
        num_chunks = 7
        chunks = [chunk_size] * 6 + [frame_bytes - 6 * chunk_size]
        self.assertEqual(sum(chunks), frame_bytes)
        self.assertEqual(chunks[-1], 460800)

        # On USB 3.0 SuperSpeed: usable payload rate ~380 MB/s
        usb3_usable_rate = 380.0 * 1024 * 1024  # B/s
        total_transfer_time_s = sum(c / usb3_usable_rate for c in chunks)
        total_transfer_time_ms = total_transfer_time_s * 1000.0

        # Entire 7-chunk frame transfers in ~11 ms
        self.assertLess(total_transfer_time_ms, 15.0)

        # At 24.0 fps (period = 41.67 ms), bus time is under 30% of interval
        frame_period_24fps_ms = 1000.0 / 24.0
        bus_duty_cycle_24fps = (total_transfer_time_ms / frame_period_24fps_ms) * 100.0
        self.assertLess(bus_duty_cycle_24fps, 35.0)

        # At 30.0 fps (period = 33.33 ms), bus time is under 40% of interval
        frame_period_30fps_ms = 1000.0 / 30.0
        bus_duty_cycle_30fps = (total_transfer_time_ms / frame_period_30fps_ms) * 100.0
        self.assertLess(bus_duty_cycle_30fps, 45.0)

    def test_destination_sds_category_1_cmp11_mitigation(self):
        """Validate destination SDS contains Category 1 (YcStateInfo) to eliminate CMP 11."""
        import struct

        def sds_find_entry(raw: bytes, target_cate: int):
            if len(raw) < 32 or raw[:4] != b"SSYC":
                return None
            version, count, off = struct.unpack_from("<III", raw, 8)
            if version != 1 or count > 64:
                return None
            for i in range(count):
                if off < 32 or off + 24 > len(raw):
                    return None
                mark, cate, _, data, n, nxt = struct.unpack_from("<4sIIIII", raw, off)
                if mark != b"ETRY":
                    return None
                if cate == target_cate:
                    return raw[data : data + n]
                if i + 1 < count and not nxt:
                    return None
                off = nxt
            return None

        # Build SDS with Category 0 (ImageSizeInfo) and Category 1 (YcStateInfo)
        buf = bytearray(4096)
        struct.pack_into("<4sIIII", buf, 0, b"SSYC", 0, 1, 2, 32)
        # Entry 0: Category 0 at 32, data at 64, len 60, next 128
        struct.pack_into("<4sIIIII", buf, 32, b"ETRY", 0, 0, 64, 60, 128)
        # Entry 1: Category 1 at 128, data at 160, len 6, next 0
        struct.pack_into("<4sIIIII", buf, 128, b"ETRY", 1, 0, 160, 6, 0)
        # Category 0 wire: image_attach=1, unit_type=0x127, unit_handle=0x13d0, 1920x1080
        struct.pack_into("<B3xIH", buf, 64, 1, 0x127, 0x13D0)
        struct.pack_into("<HHHHHHHH", buf, 64 + 0x18, 1920, 1080, 0, 0, 1920, 1080, 0, 0)
        buf[64 + 0x2F] = 0  # yc_compress = 0 (uncompressed)
        # Category 1 wire: BT.709 colorimetry = 5, progressive scanline = 0
        buf[160:166] = bytes([0, 5, 0, 0, 0, 0])

        cat0 = sds_find_entry(bytes(buf), 0)
        cat1 = sds_find_entry(bytes(buf), 1)

        self.assertIsNotNone(cat0, "Category 0 (ImageSizeInfo) must be present in destination SDS")
        self.assertEqual(len(cat0), 60)
        self.assertIsNotNone(cat1, "Category 1 (YcStateInfo) must be present in destination SDS to prevent CMP 11")
        self.assertEqual(len(cat1), 6)
        self.assertEqual(cat1[1], 5, "Colorimetry must be BT.709 (0x05)")
        self.assertEqual(cat1[3], 0, "Scanline must be progressive (0x00)")

    def test_hd_usb3_build_artifacts(self):
        """Build the current recipe and verify its complete package."""
        repo_root = Path(__file__).resolve().parent.parent
        workspace = repo_root / ".local/work"
        workspace.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="hd-package-test-", dir=workspace)
        self.addCleanup(temporary.cleanup)
        source = Path(temporary.name) / "source"
        recipe = repo_root / "research/firmware/yuy2_transport_v43_usb3_hd"
        shutil.copytree(
            recipe, source,
            ignore=shutil.ignore_patterns("__pycache__", "*.exe", "*.o", "*.su"),
        )
        out_dir = Path(temporary.name) / "package"
        baseline = repo_root / ".local/dumps/staged/uvc/encoder-workspace-fix/candidate-1080p/libInfraStreamingUsb.so"
        kernel = repo_root / ".local/outputs/hd-v43/usbg_video.ko"
        command = [
            sys.executable, "-B", str(source / "recipe/build.py"),
            "--repo", str(repo_root), "--output", str(out_dir),
            "--streaming-image", str(baseline), "--kernel", str(kernel),
        ]
        result = subprocess.run(
            command,
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        manifest_path = out_dir / "manifest.json"
        self.assertTrue(manifest_path.is_file(), f"Missing {manifest_path}")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest.get("revision"), "4.6-1080p-usb3-24fps-candidate")
        self.assertEqual(manifest.get("status"), "BUILT_NOT_HARDWARE_VERIFIED")
        self.assertEqual(manifest.get("deployment"), "NOT_INSTALLED")
        self.assertEqual(manifest.get("width"), 1920)
        self.assertEqual(manifest.get("height"), 1080)
        self.assertEqual(manifest.get("advertised_fps"), 24)
        self.assertEqual(manifest.get("frame_bytes"), 4147200)

        # Check compiled files and packaging
        v43_so = out_dir / "yuy2_1080_v43chunk.so"
        self.assertTrue(v43_so.is_file())
        self.assertGreater(v43_so.stat().st_size, 30000)

        usb_so = out_dir / "libInfraStreamingUsb.so"
        self.assertTrue(usb_so.is_file())
        self.assertGreater(usb_so.stat().st_size, 50000)

        kmod = out_dir / "usbg_video.ko"
        self.assertTrue(kmod.is_file())
        kernel_md5 = hashlib.md5(kernel.read_bytes()).hexdigest()
        self.assertEqual(manifest.get("required_kernel_md5"), kernel_md5)
        self.assertEqual(kmod.read_bytes(), kernel.read_bytes())

        # Verify deployment and safety scripts
        install_sh = out_dir / "install.sh"
        self.assertTrue(install_sh.is_file())
        install_content = install_sh.read_text(encoding="utf-8")
        manifest_files = manifest.get("files", {})
        v43_md5 = manifest_files["yuy2_1080_v43chunk.so"]["md5"]
        self.assertIn("9f197ff9b300e49ab531b6f9e794253e", install_content, "DmmConfig.bin guard required")
        self.assertIn(v43_md5, install_content, "v43 chunk so guard required")
        self.assertIn(kernel_md5, install_content, "usbg_video.ko guard required")
        self.assertIn(manifest_files["libInfraStreamingUsb.so"]["md5"], install_content)

        rollback_sh = out_dir / "rollback.sh"
        self.assertTrue(rollback_sh.is_file())

        # Verify manifest files hash table
        manifest_files = manifest.get("files", {})
        self.assertIn("yuy2_1080_v43chunk.so", manifest_files)
        self.assertIn("libInfraStreamingUsb.so", manifest_files)
        self.assertIn("usbg_video.ko", manifest_files)
        self.assertIn("install.sh", manifest_files)
        self.assertIn("rollback.sh", manifest_files)

        for fname, finfo in manifest_files.items():
            fpath = out_dir / fname
            self.assertTrue(fpath.is_file(), f"Missing packaged file: {fname}")
            data = fpath.read_bytes()
            self.assertEqual(finfo["bytes"], len(data), fname)
            self.assertEqual(finfo["md5"], hashlib.md5(data).hexdigest(), fname)
            self.assertEqual(finfo["sha256"], hashlib.sha256(data).hexdigest(), fname)

        # A failed rebuild must not leave a success manifest for partial output.
        failed = subprocess.run(
            [*command, "--cc", str(source / "missing-compiler")],
            capture_output=True, text=True, timeout=120,
        )
        self.assertNotEqual(failed.returncode, 0)
        self.assertFalse(manifest_path.exists())



if __name__ == "__main__":
    unittest.main()
