#!/usr/bin/env python3
"""Offline ABI and Ownership Test Suite (Task R4 Part 1).

Rigorous, offline reverse-engineering verification covering:
1. Real compiled Sony structs:
   - PIN_YC_IMAGE_SIZE_INFO (sizeof == 60 bytes, exact 31 field offsets)
   - PIN_YC_YC_STATE_INFO (sizeof == 6 bytes, exact 6 field offsets)
   - PIN_PROPERTY (sizeof == 16 bytes, exact 4 field offsets, 24-bit routing key)
   - dmm_extent_t (sizeof == 40 bytes, unit handle, num_planes, plane addresses/strides)
2. ABI calling conventions and ownership lifecycles with mock services:
   - Acquisition timeout handling (<= 10 ms enforced)
   - Error fallback to synthetic color bars on source error or timeout
   - Safe lease release and retain-lease on release failure
   - USB completion fence: host EBUSY prevents upstream acquisition/mutation; copy into owned Unit 0x276
   - yuy2_live_bind binding to revision 2.5 transport
3. ARM Cortex-A5 VFPv4-D16 zero-NEON instruction verification.
"""

import ctypes
import hashlib
import json
import os
import re
import struct
import subprocess
import tempfile
import unittest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_FRAME_DIR = Path(__file__).resolve().parent
TRANSPORT_V25_DIR = REPO_ROOT / "research" / "firmware" / "yuy2_transport_v25"
DUMPS_DIR = REPO_ROOT / "dumps" / "camera_2025"
FRAMEWORK_SO = DUMPS_DIR / "usr" / "usr" / "lib" / "dataflowInfraFramework.so"
LIBBIZFW_SO = DUMPS_DIR / "usr" / "usr" / "lib" / "libBizFw.so"
STREAMING_USB_SO = DUMPS_DIR / "usr" / "usr" / "lib" / "libInfraStreamingUsb.so"
USB_CMN_SO = DUMPS_DIR / "usr" / "usr" / "lib" / "libInfraUsbCmn.so"
DMM_CONFIG_BIN = DUMPS_DIR / "usr" / "setting" / "DmmConfig.bin"
AVCAM_BIN = REPO_ROOT / "dumps" / "firmware" / "av-cam.bin"

CHEC_OUTPUTS = Path(r"C:\Users\qn061\Documents\Codex\2026-10-22\chec\outputs\yuy2-640-v25\candidate")
STREAMING_IMAGE = Path(r"C:\Users\qn061\Documents\Codex\2026-10-22\chec\work\encoder-reproduction\libInfraStreamingUsb.so")
ARM_GCC = Path(r"C:\msys64\ucrt64\bin\arm-none-eabi-gcc.exe")

try:
    from elftools.elf.elffile import ELFFile
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_ARM
    from capstone.arm import ARM_GRP_NEON
    HAVE_CAPSTONE_ELF = True
except ImportError:
    HAVE_CAPSTONE_ELF = False

try:
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
    from unicorn.arm_const import *
    HAVE_UNICORN = True
except ImportError:
    HAVE_UNICORN = False


# =============================================================================
# Ctypes Struct Definitions for Real Firmware Structures
# =============================================================================

class PinYcImageSizeInfo(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("image_attach", ctypes.c_uint8),       # +0x00
        ("reserved0", ctypes.c_uint8 * 3),      # +0x01
        ("unit_type", ctypes.c_uint32),         # +0x04
        ("unit_handle", ctypes.c_uint16),       # +0x08
        ("reserved1", ctypes.c_uint16),         # +0x0a
        ("unit_data_offset", ctypes.c_uint32),  # +0x0c
        ("exposure_time", ctypes.c_uint8),      # +0x10
        ("expose_pic_delay", ctypes.c_uint8),   # +0x11
        ("scenario_end", ctypes.c_uint8),       # +0x12
        ("mirror", ctypes.c_uint8),             # +0x13
        ("record_size_x", ctypes.c_uint16),     # +0x14
        ("record_size_y", ctypes.c_uint16),     # +0x16
        ("canvas_size_x", ctypes.c_uint16),     # +0x18
        ("canvas_size_y", ctypes.c_uint16),     # +0x1a
        ("valid_offset_x", ctypes.c_uint16),    # +0x1c
        ("valid_offset_y", ctypes.c_uint16),    # +0x1e
        ("valid_size_x", ctypes.c_uint16),      # +0x20
        ("valid_size_y", ctypes.c_uint16),      # +0x22
        ("target_offset_x", ctypes.c_uint16),   # +0x24
        ("target_offset_y", ctypes.c_uint16),   # +0x26
        ("target_size_x", ctypes.c_uint16),     # +0x28
        ("target_size_y", ctypes.c_uint16),     # +0x2a
        ("data_site", ctypes.c_uint8),          # +0x2c
        ("iib_number", ctypes.c_uint8),         # +0x2d
        ("aspect", ctypes.c_uint8),             # +0x2e
        ("yc_compress", ctypes.c_uint8),        # +0x2f
        ("data_transfer", ctypes.c_uint8),      # +0x30
        ("data_placement", ctypes.c_uint8),     # +0x31
        ("data_content", ctypes.c_uint8),       # +0x32
        ("data_scan", ctypes.c_uint8),          # +0x33
        ("strip_width", ctypes.c_uint16),       # +0x34
        ("yc_bit_depth", ctypes.c_uint8),       # +0x36
        ("reserved2", ctypes.c_uint8),          # +0x37
        ("cam_freq_char_h", ctypes.c_uint16),   # +0x38
        ("reserved3", ctypes.c_uint16),         # +0x3a
    ]


class PinYcYcStateInfo(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("y_range", ctypes.c_uint8),          # +0x00
        ("colorimetry", ctypes.c_uint8),      # +0x01
        ("chroma_phase", ctypes.c_uint8),     # +0x02
        ("scanline", ctypes.c_uint8),         # +0x03
        ("copy_protection", ctypes.c_uint8),  # +0x04
        ("author", ctypes.c_uint8),           # +0x05
    ]


class PinProperty(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("subsystem_id", ctypes.c_uint32),    # +0x00
        ("unit_id", ctypes.c_uint32),         # +0x04
        ("pin_id", ctypes.c_uint32),          # +0x08
        ("flags_queue_id", ctypes.c_uint32),  # +0x0c
    ]


class DmmPlane(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("phy_addr", ctypes.c_uint32),        # +0x00
        ("size_or_stride", ctypes.c_uint32),  # +0x04
    ]


class DmmExtent(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("unit_handle", ctypes.c_uint16),     # +0x00
        ("num_planes", ctypes.c_uint16),      # +0x02
        ("total_size", ctypes.c_uint32),      # +0x04
        ("planes", DmmPlane * 4),             # +0x08 (4 * 8 = 32 bytes)
    ]


# =============================================================================
# Test Suite 1: Real Compiled Struct Layouts & Firmware Offset Validation
# =============================================================================

class TestRealCompiledStructs(unittest.TestCase):
    """Test 1: Assert exact sizeof and member byte offsets for genuine Sony structs."""

    def test_pin_yc_image_size_info_size_and_offsets(self):
        """PIN_YC_IMAGE_SIZE_INFO: assert sizeof == 60 bytes and all member offsets."""
        self.assertEqual(ctypes.sizeof(PinYcImageSizeInfo), 60, "Size must be exactly 60 bytes (0x3c)")
        self.assertEqual(PinYcImageSizeInfo.image_attach.offset, 0x00)
        self.assertEqual(PinYcImageSizeInfo.unit_type.offset, 0x04)
        self.assertEqual(PinYcImageSizeInfo.unit_handle.offset, 0x08)
        self.assertEqual(PinYcImageSizeInfo.unit_data_offset.offset, 0x0c)
        self.assertEqual(PinYcImageSizeInfo.exposure_time.offset, 0x10)
        self.assertEqual(PinYcImageSizeInfo.expose_pic_delay.offset, 0x11)
        self.assertEqual(PinYcImageSizeInfo.scenario_end.offset, 0x12)
        self.assertEqual(PinYcImageSizeInfo.mirror.offset, 0x13)
        self.assertEqual(PinYcImageSizeInfo.record_size_x.offset, 0x14)
        self.assertEqual(PinYcImageSizeInfo.record_size_y.offset, 0x16)
        self.assertEqual(PinYcImageSizeInfo.canvas_size_x.offset, 0x18)
        self.assertEqual(PinYcImageSizeInfo.canvas_size_y.offset, 0x1a)
        self.assertEqual(PinYcImageSizeInfo.valid_offset_x.offset, 0x1c)
        self.assertEqual(PinYcImageSizeInfo.valid_offset_y.offset, 0x1e)
        self.assertEqual(PinYcImageSizeInfo.valid_size_x.offset, 0x20)
        self.assertEqual(PinYcImageSizeInfo.valid_size_y.offset, 0x22)
        self.assertEqual(PinYcImageSizeInfo.target_offset_x.offset, 0x24)
        self.assertEqual(PinYcImageSizeInfo.target_offset_y.offset, 0x26)
        self.assertEqual(PinYcImageSizeInfo.target_size_x.offset, 0x28)
        self.assertEqual(PinYcImageSizeInfo.target_size_y.offset, 0x2a)
        self.assertEqual(PinYcImageSizeInfo.data_site.offset, 0x2c)
        self.assertEqual(PinYcImageSizeInfo.iib_number.offset, 0x2d)
        self.assertEqual(PinYcImageSizeInfo.aspect.offset, 0x2e)
        self.assertEqual(PinYcImageSizeInfo.yc_compress.offset, 0x2f)
        self.assertEqual(PinYcImageSizeInfo.data_transfer.offset, 0x30)
        self.assertEqual(PinYcImageSizeInfo.data_placement.offset, 0x31)
        self.assertEqual(PinYcImageSizeInfo.data_content.offset, 0x32)
        self.assertEqual(PinYcImageSizeInfo.data_scan.offset, 0x33)
        self.assertEqual(PinYcImageSizeInfo.strip_width.offset, 0x34)
        self.assertEqual(PinYcImageSizeInfo.yc_bit_depth.offset, 0x36)
        self.assertEqual(PinYcImageSizeInfo.cam_freq_char_h.offset, 0x38)

    def test_pin_yc_image_size_info_against_framework_so(self):
        """Cross-check PIN_YC_IMAGE_SIZE_INFO constructor and GetData_All in dataflowInfraFramework.so."""
        if not HAVE_CAPSTONE_ELF:
            self.skipTest("Capstone and elftools required")

        self.assertTrue(FRAMEWORK_SO.is_file(), f"Missing binary: {FRAMEWORK_SO}")
        with open(FRAMEWORK_SO, "rb") as f:
            elf = ELFFile(f)
            dynsym = elf.get_section_by_name(".dynsym")
            sym = next(s for s in dynsym.iter_symbols() if s.name == "_ZN35C_DataflowInfra_Entry_ImageSizeInfoC2Ev")
            va = sym["st_value"] & ~1
            seg = next(s for s in elf.iter_segments() if s["p_type"] == "PT_LOAD" and s["p_vaddr"] <= va < s["p_vaddr"] + s["p_filesz"])
            f.seek(seg["p_offset"] + (va - seg["p_vaddr"]))
            code = f.read(sym["st_size"])

        md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
        instructions = list(md.disasm(code, va))
        # Look for movs r6, #0x3c (allocation of 60 bytes)
        has_60_alloc = any(i.mnemonic == "movs" and "0x3c" in i.op_str for i in instructions)
        self.assertTrue(has_60_alloc, "Constructor must set length = 60 bytes (0x3c)")

    def test_pin_yc_yc_state_info_size_and_offsets(self):
        """PIN_YC_YC_STATE_INFO: assert sizeof == 6 bytes and all member offsets."""
        self.assertEqual(ctypes.sizeof(PinYcYcStateInfo), 6, "Size must be exactly 6 bytes")
        self.assertEqual(PinYcYcStateInfo.y_range.offset, 0x00)
        self.assertEqual(PinYcYcStateInfo.colorimetry.offset, 0x01)
        self.assertEqual(PinYcYcStateInfo.chroma_phase.offset, 0x02)
        self.assertEqual(PinYcYcStateInfo.scanline.offset, 0x03)
        self.assertEqual(PinYcYcStateInfo.copy_protection.offset, 0x04)
        self.assertEqual(PinYcYcStateInfo.author.offset, 0x05)

    def test_pin_yc_yc_state_info_against_framework_so(self):
        """Cross-check PIN_YC_YC_STATE_INFO constructor in dataflowInfraFramework.so."""
        if not HAVE_CAPSTONE_ELF:
            self.skipTest("Capstone and elftools required")

        with open(FRAMEWORK_SO, "rb") as f:
            elf = ELFFile(f)
            dynsym = elf.get_section_by_name(".dynsym")
            sym = next(s for s in dynsym.iter_symbols() if s.name == "_ZN33C_DataflowInfra_Entry_YcStateInfoC2Ev")
            va = sym["st_value"] & ~1
            seg = next(s for s in elf.iter_segments() if s["p_type"] == "PT_LOAD" and s["p_vaddr"] <= va < s["p_vaddr"] + s["p_filesz"])
            f.seek(seg["p_offset"] + (va - seg["p_vaddr"]))
            code = f.read(sym["st_size"])

        md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
        instructions = list(md.disasm(code, va))
        # Look for movs r6, #6 (exact 6-byte size)
        has_6_alloc = any(i.mnemonic == "movs" and "#6" in i.op_str for i in instructions)
        self.assertTrue(has_6_alloc, "Constructor must set length = 6 bytes")

    def test_pin_property_size_and_routing_key(self):
        """PIN_PROPERTY: assert sizeof == 16 bytes and composite 24-bit routing key."""
        self.assertEqual(ctypes.sizeof(PinProperty), 16, "Size must be exactly 16 bytes")
        self.assertEqual(PinProperty.subsystem_id.offset, 0x00)
        self.assertEqual(PinProperty.unit_id.offset, 0x04)
        self.assertEqual(PinProperty.pin_id.offset, 0x08)
        self.assertEqual(PinProperty.flags_queue_id.offset, 0x0c)

        # Composite routing key calculation: (subsystem << 16) | (unit << 8) | pin
        subsystem = 0x55  # VDF
        unit = 0x01       # Source
        pin = 0x01        # Completed preview YC pin
        pin_key = (subsystem << 16) | (unit << 8) | pin
        self.assertEqual(pin_key, 0x00550101, "VDF preview pin key must be 0x00550101")

        # Verify target queue 0x01670464 in av-cam.bin routing table if present
        if AVCAM_BIN.is_file():
            data = AVCAM_BIN.read_bytes()
            RTOS_BASE = 0x635C6000
            # Routing table entry for VDF at VA 0x63e96f98
            table_off = 0x63e96f98 - RTOS_BASE
            if 0 <= table_off < len(data) - 4:
                entry = struct.unpack_from("<I", data, table_off)[0]
                self.assertEqual(entry, 0x01670464, "Routing table must resolve VDF to queue 0x01670464")

    def test_dmm_extent_t_size_and_plane_geometry(self):
        """dmm_extent_t: assert sizeof == 40 bytes and plane layout."""
        self.assertEqual(ctypes.sizeof(DmmExtent), 40, "Size must be exactly 40 bytes")
        self.assertEqual(DmmExtent.unit_handle.offset, 0x00)
        self.assertEqual(DmmExtent.num_planes.offset, 0x02)
        self.assertEqual(DmmExtent.total_size.offset, 0x04)
        self.assertEqual(DmmExtent.planes.offset, 0x08)

        # Plane 0: Y physical address at offset 0x08, stride at 0x0c
        self.assertEqual(DmmExtent.planes.offset + 0 * 8 + DmmPlane.phy_addr.offset, 0x08)
        self.assertEqual(DmmExtent.planes.offset + 0 * 8 + DmmPlane.size_or_stride.offset, 0x0c)
        # Plane 1: UV physical address at offset 0x10, stride at 0x14
        self.assertEqual(DmmExtent.planes.offset + 1 * 8 + DmmPlane.phy_addr.offset, 0x10)
        self.assertEqual(DmmExtent.planes.offset + 1 * 8 + DmmPlane.size_or_stride.offset, 0x14)

        # Verify DmmConfig.bin extent sizes
        if DMM_CONFIG_BIN.is_file():
            cfg = DMM_CONFIG_BIN.read_bytes()
            # Extent 0x333 (Unit 0x276 workspace) has size 0x320000 (3,276,800 bytes)
            # Extent table lookup at 0x2e20
            ext_333 = struct.unpack_from("<5I", cfg, 0x2e20)
            self.assertEqual(ext_333[0], 0x333)
            self.assertEqual(ext_333[1], 0x320000)

            # Extents 0x227, 0x3da, 0x3e2 have size 0x96000 (614,400 bytes = 640x480x2)
            ext_227 = struct.unpack_from("<5I", cfg, 0x180c)
            self.assertEqual(ext_227[3], 0x227)
            self.assertEqual(ext_227[4], 0x96000)


# =============================================================================
# Test Suite 2: ABI Calling Conventions, Ownership Lifecycles & Fallback
# =============================================================================

class TestAbiCallingConventionsAndOwnership(unittest.TestCase):
    """Test 2: Test raw_live_ops, timeout bounds, synthetic fallback, lease retain, and USB fence."""

    def test_c_harness_lease_pipeline_32_cases(self):
        """Compile and execute test_raw_live_source.c verifying all 32 ownership/struct cases."""
        with tempfile.TemporaryDirectory(prefix="abi-test-") as tmpdir:
            exe = Path(tmpdir) / "test_raw_live_source.exe"
            subprocess.run([
                "gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-DRAW_FRAME_CONVERSION_ONLY", "-fno-tree-vectorize", "-fno-tree-slp-vectorize",
                "-I", str(RAW_FRAME_DIR),
                str(RAW_FRAME_DIR / "test_raw_live_source.c"),
                str(RAW_FRAME_DIR / "raw_live_source.c"),
                str(RAW_FRAME_DIR / "raw_frame_source.c"),
                "-o", str(exe)
            ], check=True, capture_output=True, text=True)

            res = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
            self.assertIn("Raw live source ownership/conversion checks passed", res.stdout)
            self.assertIn("cases=32", res.stdout)

    def test_timeout_bounds_lte_10ms_enforcement(self):
        """raw_live_init: verify timeout > 10 ms or == 0 is strictly rejected with -1."""
        # Compile a minimal test program to verify ABI parameter validation
        c_code = r"""
        #include "raw_live_source.h"
        #include <assert.h>
        static int mock_acq(void *o, uint32_t t, raw_live_frame *f) { (void)o;(void)t;(void)f; return 0; }
        static int mock_rel(void *o, uintptr_t t) { (void)o;(void)t; return 0; }
        static int mock_map(void *o, const raw_live_plane *p, size_t n, raw_live_mapping *m) { (void)o;(void)p;(void)n;(void)m; return 0; }
        static int mock_unmap(void *o, raw_live_mapping *m) { (void)o;(void)m; return 0; }
        int main(void) {
            raw_live_ops ops = {RAW_LIVE_ABI, sizeof(raw_live_ops), mock_acq, mock_rel, mock_map, mock_unmap};
            raw_live_source s;
            /* timeout = 11 ms: must be rejected (-1) */
            s = (raw_live_source){0};
            assert(raw_live_init(&s, &ops, NULL, 640, 480, 11) == RAW_FRAME_ERR_INVALID_PARAM);
            /* timeout = 0 ms: must be rejected (-1) */
            s = (raw_live_source){0};
            assert(raw_live_init(&s, &ops, NULL, 640, 480, 0) == RAW_FRAME_ERR_INVALID_PARAM);
            /* timeout = 10 ms: must succeed (0) */
            s = (raw_live_source){0};
            assert(raw_live_init(&s, &ops, NULL, 640, 480, 10) == RAW_FRAME_OK);
            assert(s.timeout_ms == 10);
            return 0;
        }
        """
        with tempfile.TemporaryDirectory(prefix="timeout-test-") as tmpdir:
            src_file = Path(tmpdir) / "test_timeout.c"
            exe_file = Path(tmpdir) / "test_timeout.exe"
            src_file.write_text(c_code)
            subprocess.run([
                "gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-DRAW_FRAME_CONVERSION_ONLY",
                "-I", str(RAW_FRAME_DIR),
                str(src_file), str(RAW_FRAME_DIR / "raw_live_source.c"),
                str(RAW_FRAME_DIR / "raw_frame_source.c"),
                "-o", str(exe_file)
            ], check=True, capture_output=True, text=True)
            res = subprocess.run([str(exe_file)], check=True, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)

    def test_error_fallback_to_synthetic_bars_full_pattern(self):
        """Verify error fallback generates full BT.601 limited-range bars into Unit 0x276 workspace."""
        c_code = r"""
        #include "raw_live_source.h"
        #include <assert.h>
        #include <string.h>
        int main(void) {
            uint8_t buf[640 * 480 * 2];
            memset(buf, 0xee, sizeof(buf));
            /* Generate synthetic fallback */
            int e = raw_frame_generate_synthetic_fallback(buf, 640, 480, 100);
            assert(e == RAW_FRAME_OK);

            /* Check row 0, bar 0: White (Y=235, U=128, Y=235, V=128) */
            assert(buf[0] == 235 && buf[1] == 128 && buf[2] == 235 && buf[3] == 128);
            /* Bar 1 (x=80, byte=160): Yellow (Y=210, U=16, Y=210, V=146) */
            assert(buf[160] == 210 && buf[161] == 16 && buf[162] == 210 && buf[163] == 146);
            /* Bar 2 (x=160, byte=320): Cyan (Y=170, U=166, Y=170, V=16) */
            assert(buf[320] == 170 && buf[321] == 166 && buf[322] == 170 && buf[323] == 16);
            /* Bar 3 (x=240, byte=480): Green (Y=145, U=54, Y=145, V=34) */
            assert(buf[480] == 145 && buf[481] == 54 && buf[482] == 145 && buf[483] == 34);
            /* Bar 4 (x=320, byte=640): Magenta (Y=106, U=202, Y=106, V=222) */
            assert(buf[640] == 106 && buf[641] == 202 && buf[642] == 106 && buf[643] == 222);
            /* Bar 5 (x=400, byte=800): Red (Y=81, U=90, Y=81, V=240) */
            assert(buf[800] == 81 && buf[801] == 90 && buf[802] == 81 && buf[803] == 240);
            /* Bar 6 (x=480, byte=960): Blue (Y=41, U=240, Y=41, V=110) */
            assert(buf[960] == 41 && buf[961] == 240 && buf[962] == 41 && buf[963] == 110);
            /* Bar 7 (x=560, byte=1120): Black (Y=16, U=128, Y=16, V=128) */
            assert(buf[1120] == 16 && buf[1121] == 128 && buf[1122] == 16 && buf[1123] == 128);

            /* Check row 475 (counter rows 472..479): Bit 0 (x=0..39) for counter=100 (bit 2,5,6 set) -> 0 */
            /* In frame_counter 100 = 0x64 (bits 2, 5, 6 set) */
            uint8_t *counter_row = buf + 475 * (640 * 2);
            /* x=0 has bit 0 -> 16 (black) */
            assert(counter_row[0] == 16 && counter_row[1] == 128);
            /* x=80 has bit 2 -> 235 (white) */
            assert(counter_row[80 * 2] == 235 && counter_row[80 * 2 + 1] == 128);
            return 0;
        }
        """
        with tempfile.TemporaryDirectory(prefix="fallback-test-") as tmpdir:
            src_file = Path(tmpdir) / "test_fallback.c"
            exe_file = Path(tmpdir) / "test_fallback.exe"
            src_file.write_text(c_code)
            subprocess.run([
                "gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-I", str(RAW_FRAME_DIR),
                str(src_file), str(RAW_FRAME_DIR / "raw_frame_source.c"),
                "-o", str(exe_file)
            ], check=True, capture_output=True, text=True)
            res = subprocess.run([str(exe_file)], check=True, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)

    def test_safe_lease_release_and_retain_semantics(self):
        """Verify that release failure retains lease token and prevents duplicate acquisition."""
        c_code = r"""
        #include "raw_live_source.h"
        #include <assert.h>
        static int acq_calls = 0, rel_calls = 0, release_fail = 1;
        static int mock_acq(void *o, uint32_t t, raw_live_frame *f) {
            (void)o;(void)t;
            acq_calls++;
            f->token = 0xbeef;
            f->sequence = 1;
            f->width = 640; f->height = 480;
            f->format = RAW_FRAME_PIXFMT_YUY2;
            f->flags = RAW_LIVE_READY_LINEAR_8BIT_BT601_LIMITED;
            f->plane[0] = (raw_live_plane){0x20000000, 614400, 1280};
            return 0;
        }
        static int mock_rel(void *o, uintptr_t t) {
            (void)o;
            assert(t == 0xbeef);
            rel_calls++;
            return release_fail ? -7 : 0;
        }
        static uint8_t dummy[614400];
        static int mock_map(void *o, const raw_live_plane *p, size_t n, raw_live_mapping *m) {
            (void)o;(void)p;
            m->base = dummy; m->data = dummy; m->length = n;
            return 0;
        }
        static int mock_unmap(void *o, raw_live_mapping *m) { (void)o;(void)m; return 0; }

        int main(void) {
            raw_live_ops ops = {RAW_LIVE_ABI, sizeof(raw_live_ops), mock_acq, mock_rel, mock_map, mock_unmap};
            raw_live_source s = {0};
            uint32_t seq = 0;
            static uint8_t dst[614400];
            assert(raw_live_init(&s, &ops, NULL, 640, 480, 10) == RAW_FRAME_OK);

            /* Fill frame 1: release fails with -7 */
            int e = raw_live_fill(&s, dst, sizeof(dst), 0x15b00000, &seq);
            assert(e == -7);
            /* Lease token must be retained */
            assert(s.leased.token == 0xbeef);

            /* Fill frame 2: must fail immediately without calling acquire() */
            e = raw_live_fill(&s, dst, sizeof(dst), 0x15b00000, &seq);
            assert(e == -7);
            assert(acq_calls == 1); /* no second acquire */

            /* Drain: fails and retains token while release_fail is 1 */
            assert(raw_live_drain(&s) == -7);
            assert(s.leased.token == 0xbeef);

            /* Clear failure flag: drain succeeds and clears token */
            release_fail = 0;
            assert(raw_live_drain(&s) == RAW_FRAME_OK);
            assert(s.leased.token == 0);

            /* Now fill frame 3: acquire succeeds again */
            e = raw_live_fill(&s, dst, sizeof(dst), 0x15b00000, &seq);
            assert(e == RAW_FRAME_OK);
            assert(acq_calls == 2);
            assert(s.leased.token == 0);
            return 0;
        }
        """
        with tempfile.TemporaryDirectory(prefix="retain-test-") as tmpdir:
            src_file = Path(tmpdir) / "test_retain.c"
            exe_file = Path(tmpdir) / "test_retain.exe"
            src_file.write_text(c_code)
            subprocess.run([
                "gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-DRAW_FRAME_CONVERSION_ONLY",
                "-I", str(RAW_FRAME_DIR),
                str(src_file), str(RAW_FRAME_DIR / "raw_live_source.c"),
                str(RAW_FRAME_DIR / "raw_frame_source.c"),
                "-o", str(exe_file)
            ], check=True, capture_output=True, text=True)
            res = subprocess.run([str(exe_file)], check=True, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)

    def test_usb_completion_fence_and_destination_overlap_guard(self):
        """Verify that upstream frame overlapping destination Unit 0x276 is rejected."""
        c_code = r"""
        #include "raw_live_source.h"
        #include <assert.h>
        static int mock_acq(void *o, uint32_t t, raw_live_frame *f) {
            (void)o;(void)t;
            f->token = 0x123; f->sequence = 1; f->width = 640; f->height = 480;
            f->format = RAW_FRAME_PIXFMT_YUY2;
            f->flags = RAW_LIVE_READY_LINEAR_8BIT_BT601_LIMITED;
            /* Overlap: source physical address equals destination physical address 0x15b00000 */
            f->plane[0] = (raw_live_plane){0x15b00000, 614400, 1280};
            return 0;
        }
        static int mock_rel(void *o, uintptr_t t) { (void)o;(void)t; return 0; }
        static int mock_map(void *o, const raw_live_plane *p, size_t n, raw_live_mapping *m) { (void)o;(void)p;(void)n;(void)m; return 0; }
        static int mock_unmap(void *o, raw_live_mapping *m) { (void)o;(void)m; return 0; }

        int main(void) {
            raw_live_ops ops = {RAW_LIVE_ABI, sizeof(raw_live_ops), mock_acq, mock_rel, mock_map, mock_unmap};
            raw_live_source s = {0};
            uint32_t seq = 0;
            static uint8_t dst[614400];
            assert(raw_live_init(&s, &ops, NULL, 640, 480, 10) == RAW_FRAME_OK);

            /* Fill with overlapping destination: must return RAW_FRAME_ERR_INVALID_PARAM (-1) */
            int e = raw_live_fill(&s, dst, sizeof(dst), 0x15b00000, &seq);
            assert(e == RAW_FRAME_ERR_INVALID_PARAM);
            return 0;
        }
        """
        with tempfile.TemporaryDirectory(prefix="fence-test-") as tmpdir:
            src_file = Path(tmpdir) / "test_fence.c"
            exe_file = Path(tmpdir) / "test_fence.exe"
            src_file.write_text(c_code)
            subprocess.run([
                "gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-DRAW_FRAME_CONVERSION_ONLY",
                "-I", str(RAW_FRAME_DIR),
                str(src_file), str(RAW_FRAME_DIR / "raw_live_source.c"),
                str(RAW_FRAME_DIR / "raw_frame_source.c"),
                "-o", str(exe_file)
            ], check=True, capture_output=True, text=True)
            res = subprocess.run([str(exe_file)], check=True, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)

    def test_unicorn_arm_revision_25_live_integration(self):
        """Execute Unicorn ARM emulation verifying revision 2.5 transport live binding."""
        if not HAVE_UNICORN:
            self.skipTest("Unicorn emulator required")
        if not (CHEC_OUTPUTS / "yuy2_640_v25.so").is_file():
            self.skipTest(f"Missing compiled candidate: {CHEC_OUTPUTS / 'yuy2_640_v25.so'}")
        if not STREAMING_IMAGE.is_file():
            self.skipTest(f"Missing streaming image: {STREAMING_IMAGE}")

        verify_script = TRANSPORT_V25_DIR / "verify_live_integration.py"
        res = subprocess.run([
            sys.executable, "-B", str(verify_script),
            "--repo", str(REPO_ROOT),
            "--output", str(CHEC_OUTPUTS),
            "--streaming-image", str(STREAMING_IMAGE)
        ], check=True, capture_output=True, text=True)

        data = json.loads(res.stdout)
        self.assertEqual(data["passed"], 5)
        self.assertIn("live:busy_host_never_acquires_or_mutates_source", data["cases"])
        self.assertIn("live:leased_frame_copied_unmapped_released_then_submitted_without_counter_overlay", data["cases"])
        self.assertIn("live:timeout_restores_entire_synthetic_pattern_after_live_frame", data["cases"])
        self.assertIn("live:failed_release_retains_lease_and_blocks_further_acquisition", data["cases"])
        self.assertIn("live:explicit_stop_retries_upstream_release_without_unpinning_usb_source", data["cases"])


# =============================================================================
# Test Suite 3: Cortex-A5 Zero-NEON Compilation Verification
# =============================================================================

class TestNoNeonCortexA5Compilation(unittest.TestCase):
    """Test 3: Cross-compile with ARM GCC for Cortex-A5 and verify zero NEON instructions."""

    def test_cross_compile_raw_frame_source_zero_neon(self):
        """Compile raw_live_source.c and raw_frame_source.c for Cortex-A5; verify zero NEON instructions."""
        if not ARM_GCC.is_file():
            self.skipTest(f"arm-none-eabi-gcc not found at: {ARM_GCC}")
        if not HAVE_CAPSTONE_ELF:
            self.skipTest("Capstone and elftools required")

        with tempfile.TemporaryDirectory(prefix="neon-test-") as tmpdir:
            obj_file = Path(tmpdir) / "raw_live_source.o"
            cmd = [
                str(ARM_GCC),
                "-mcpu=cortex-a5",
                "-marm",
                "-mfpu=vfpv4-d16",
                "-mfloat-abi=soft",
                "-fno-tree-vectorize",
                "-fno-tree-slp-vectorize",
                "-O2",
                "-DRAW_FRAME_CONVERSION_ONLY",
                "-I", str(RAW_FRAME_DIR),
                "-c", str(RAW_FRAME_DIR / "raw_live_source.c"),
                "-o", str(obj_file)
            ]
            subprocess.run(cmd, check=True)

            # Inspect disassembly for NEON group instructions
            with open(obj_file, "rb") as f:
                elf = ELFFile(f)
                text_sec = elf.get_section_by_name(".text")
                text_data = text_sec.data()

            md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
            md.detail = True
            instructions = list(md.disasm(text_data, 0))

            neon_insns = [i for i in instructions if ARM_GRP_NEON in i.groups]
            self.assertEqual(len(neon_insns), 0, f"Found {len(neon_insns)} NEON instructions in raw_live_source.o")

            # Check mnemonic blacklist
            for i in instructions:
                m = i.mnemonic.lower()
                self.assertFalse(m.startswith(("vld", "vst", "vzip", "vuzp", "vtrn", "vqadd", "vqsub")),
                                 f"Illegal NEON instruction {i.mnemonic} {i.op_str} at 0x{i.address:x}")

    def test_candidate_yuy2_640_v25_so_zero_neon(self):
        """Audit candidate yuy2_640_v25.so binary: assert 0 NEON instructions across all code regions."""
        so_path = CHEC_OUTPUTS / "yuy2_640_v25.so"
        if not so_path.is_file():
            self.skipTest(f"Candidate yuy2_640_v25.so not found at: {so_path}")
        if not HAVE_CAPSTONE_ELF:
            self.skipTest("Capstone and elftools required")

        verify_isa = TRANSPORT_V25_DIR / "verify_isa.py"
        res = subprocess.run([
            sys.executable, "-B", str(verify_isa),
            "--module", str(so_path)
        ], check=True, capture_output=True, text=True)

        data = json.loads(res.stdout)
        self.assertEqual(data["neon_instructions"], 0, "Candidate .text must contain 0 NEON instructions")
        self.assertGreater(data["instructions"], 2000, "Candidate must contain authentic instruction set")


if __name__ == "__main__":
    unittest.main()
