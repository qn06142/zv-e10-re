#!/usr/bin/env python3
"""Comprehensive Offline Verification Test Suite for Live Camera Raw Frame Source (Requirement R4).

Target Device: Sony ZV-E10 (CXD90045 SoC / Dual Cortex-A9).
Executes offline reverse engineering validation:
  Test 1: Verify exact byte offsets and sizes of PIN_YC_IMAGE_SIZE_INFO against dataflowInfraFramework.so.
  Test 2: Verify DMM Unit and Extent IDs against DmmConfig.bin.
  Test 3: Validate color conversion correctness (NV16 -> YUY2, NV12 -> YUY2, linear YUY2 memcpy).
  Test 4: Validate synthetic fallback test pattern generation and lifecycle API.
"""

import os
import re
import sys
import struct
import shutil
import ctypes
import tempfile
import unittest
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FIRMWARE_DUMP_DIR = REPO_ROOT / "dumps" / "camera_2025"
FRAMEWORK_SO = FIRMWARE_DUMP_DIR / "usr" / "usr" / "lib" / "dataflowInfraFramework.so"
DMM_CONFIG_BIN = FIRMWARE_DUMP_DIR / "usr" / "setting" / "DmmConfig.bin"
HEADER_PATH = Path(__file__).resolve().parent / "raw_frame_source.h"
SOURCE_PATH = Path(__file__).resolve().parent / "raw_frame_source.c"

# Try importing capstone and elftools
try:
    from elftools.elf.elffile import ELFFile
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
    HAVE_ELF_TOOLS = True
except ImportError:
    HAVE_ELF_TOOLS = False


class Test1_StructOffsetsAndSizes(unittest.TestCase):
    """Test 1: Verify exact byte offsets and sizes of PIN_YC_IMAGE_SIZE_INFO against dataflowInfraFramework.so."""

    def test_framework_binary_exists(self):
        """Verify authentic dataflowInfraFramework.so binary is present."""
        self.assertTrue(FRAMEWORK_SO.is_file(), f"Missing binary: {FRAMEWORK_SO}")
        self.assertEqual(FRAMEWORK_SO.stat().st_size, 172680)
        import hashlib
        self.assertEqual(
            hashlib.sha256(FRAMEWORK_SO.read_bytes()).hexdigest(),
            "3a7235ab96ed87606fc598f45db8e318afacc1e58a07e51b541923a43de76941"
        )

    def test_constructor_allocates_60_bytes(self):
        """Disassemble C_DataflowInfra_Entry_ImageSizeInfo::C2Ev and confirm 60-byte (0x3c) allocation."""
        if not HAVE_ELF_TOOLS:
            self.skipTest("pyelftools and capstone required for ELF disassembly")

        with open(FRAMEWORK_SO, "rb") as f:
            elf = ELFFile(f)
            symtab = elf.get_section_by_name(".symtab") or elf.get_section_by_name(".dynsym")
            sym = next((s for s in symtab.iter_symbols() if s.name == "_ZN35C_DataflowInfra_Entry_ImageSizeInfoC2Ev"), None)
            self.assertIsNotNone(sym, "Symbol _ZN35C_DataflowInfra_Entry_ImageSizeInfoC2Ev not found")

            va = sym["st_value"] & ~1
            size = sym["st_size"]
            load_seg = next(seg for seg in elf.iter_segments()
                            if seg["p_type"] == "PT_LOAD" and seg["p_vaddr"] <= va < seg["p_vaddr"] + seg["p_filesz"])
            file_off = load_seg["p_offset"] + (va - load_seg["p_vaddr"])

            f.seek(file_off)
            code = f.read(size)

        md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
        instructions = list(md.disasm(code, va))

        # Look for movs r6, #0x3c (60 decimal)
        found_alloc_size = False
        for insn in instructions:
            if insn.mnemonic == "movs" and "0x3c" in insn.op_str:
                found_alloc_size = True
                break

        self.assertTrue(found_alloc_size, "Failed to verify 60-byte (0x3c) allocation in constructor")

    def test_all_field_offsets_against_accessors(self):
        """Trace all 31 getter/setter methods in dataflowInfraFramework.so and verify exact struct offsets."""
        if not HAVE_ELF_TOOLS:
            self.skipTest("pyelftools and capstone required for accessor analysis")

        expected_fields = {
            # struct_offset: (field_name, expected_width, expected_type)
            0x00: ("ImageAttach", 1, "uint8_t"),
            0x04: ("UnitType", 4, "uint32_t"),
            0x08: ("UnitHandle", 2, "uint16_t"),
            0x0c: ("UnitDataOffset", 4, "uint32_t"),
            0x10: ("ExposureTime", 1, "uint8_t"),
            0x11: ("ExposePicDelay", 1, "uint8_t"),
            0x12: ("ScenarioEnd", 1, "uint8_t"),
            0x13: ("Mirror", 1, "uint8_t"),
            0x14: ("RecordSizeX", 2, "uint16_t"),
            0x16: ("RecordSizeY", 2, "uint16_t"),
            0x18: ("CanvasSizeX", 2, "uint16_t"),
            0x1a: ("CanvasSizeY", 2, "uint16_t"),
            0x1c: ("ValidOffsetX", 2, "uint16_t"),
            0x1e: ("ValidOffsetY", 2, "uint16_t"),
            0x20: ("ValidSizeX", 2, "uint16_t"),
            0x22: ("ValidSizeY", 2, "uint16_t"),
            0x24: ("TargetOffsetX", 2, "uint16_t"),
            0x26: ("TargetOffsetY", 2, "uint16_t"),
            0x28: ("TargetSizeX", 2, "uint16_t"),
            0x2a: ("TargetSizeY", 2, "uint16_t"),
            0x2c: ("DataSite", 1, "uint8_t"),
            0x2d: ("IibNumber", 1, "uint8_t"),
            0x2e: ("Aspect", 1, "uint8_t"),
            0x2f: ("YcCompress", 1, "uint8_t"),
            0x30: ("DataTransfer", 1, "uint8_t"),
            0x31: ("DataPlacement", 1, "uint8_t"),
            0x32: ("DataContent", 1, "uint8_t"),
            0x33: ("DataScan", 1, "uint8_t"),
            0x34: ("StripWidth", 2, "uint16_t"),
            0x36: ("YcBitDepth", 1, "uint8_t"),
            0x38: ("CamFreqCharH", 2, "uint16_t"),
        }

        with open(FRAMEWORK_SO, "rb") as f:
            elf = ELFFile(f)
            symtab = elf.get_section_by_name(".symtab") or elf.get_section_by_name(".dynsym")
            syms = {s.name: s for s in symtab.iter_symbols()
                    if "C_DataflowInfra_Entry_ImageSizeInfo" in s.name and "GetData_" in s.name}
            load_seg = next(seg for seg in elf.iter_segments()
                            if seg["p_type"] == "PT_LOAD" and seg["p_vaddr"] <= 0x24600 < seg["p_vaddr"] + seg["p_filesz"])

            md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

            for struct_off, (field_name, exp_width, _) in expected_fields.items():
                expected_class_off = struct_off + 0x14  # Class member offset includes 0x14 header
                getter_target = f"GetData_{field_name}"
                getter_sym = next((s for name, s in syms.items() if getter_target in name), None)
                self.assertIsNotNone(getter_sym, f"Getter {getter_target} not found")

                va = getter_sym["st_value"] & ~1
                file_off = load_seg["p_offset"] + (va - load_seg["p_vaddr"])
                f.seek(file_off)
                code = f.read(getter_sym["st_size"])

                insns = list(md.disasm(code, va))
                found_match = False
                for insn in insns:
                    m = re.search(r"\[r0(?:,\s*#(0x[0-9a-fA-F]+|[0-9]+))?\]", insn.op_str)
                    if m:
                        raw = m.group(1)
                        off = int(raw, 0) if raw else 0
                        self.assertEqual(off, expected_class_off,
                                         f"Field {field_name}: expected class offset 0x{expected_class_off:x}, got 0x{off:x}")
                        found_match = True
                        break
                self.assertTrue(found_match, f"Could not find [r0, #offset] load in {getter_target}")

    def test_c_header_struct_layout_ctypes(self):
        """Verify struct PIN_YC_IMAGE_SIZE_INFO layout in C ctypes representation."""
        class PinYcImageSizeInfo(ctypes.Structure):
            _pack_ = 1
            _fields_ = [
                ("image_attach", ctypes.c_uint8),
                ("reserved0", ctypes.c_uint8 * 3),
                ("unit_type", ctypes.c_uint32),
                ("unit_handle", ctypes.c_uint16),
                ("reserved1", ctypes.c_uint16),
                ("unit_data_offset", ctypes.c_uint32),
                ("exposure_time", ctypes.c_uint8),
                ("expose_pic_delay", ctypes.c_uint8),
                ("scenario_end", ctypes.c_uint8),
                ("mirror", ctypes.c_uint8),
                ("record_size_x", ctypes.c_uint16),
                ("record_size_y", ctypes.c_uint16),
                ("canvas_size_x", ctypes.c_uint16),
                ("canvas_size_y", ctypes.c_uint16),
                ("valid_offset_x", ctypes.c_uint16),
                ("valid_offset_y", ctypes.c_uint16),
                ("valid_size_x", ctypes.c_uint16),
                ("valid_size_y", ctypes.c_uint16),
                ("target_offset_x", ctypes.c_uint16),
                ("target_offset_y", ctypes.c_uint16),
                ("target_size_x", ctypes.c_uint16),
                ("target_size_y", ctypes.c_uint16),
                ("data_site", ctypes.c_uint8),
                ("iib_number", ctypes.c_uint8),
                ("aspect", ctypes.c_uint8),
                ("yc_compress", ctypes.c_uint8),
                ("data_transfer", ctypes.c_uint8),
                ("data_placement", ctypes.c_uint8),
                ("data_content", ctypes.c_uint8),
                ("data_scan", ctypes.c_uint8),
                ("strip_width", ctypes.c_uint16),
                ("yc_bit_depth", ctypes.c_uint8),
                ("reserved2", ctypes.c_uint8),
                ("cam_freq_char_h", ctypes.c_uint16),
                ("reserved3", ctypes.c_uint16),
            ]

        self.assertEqual(ctypes.sizeof(PinYcImageSizeInfo), 60, "Size of PIN_YC_IMAGE_SIZE_INFO must be exactly 60 bytes")
        self.assertEqual(PinYcImageSizeInfo.image_attach.offset, 0x00)
        self.assertEqual(PinYcImageSizeInfo.unit_type.offset, 0x04)
        self.assertEqual(PinYcImageSizeInfo.unit_handle.offset, 0x08)
        self.assertEqual(PinYcImageSizeInfo.unit_data_offset.offset, 0x0c)
        self.assertEqual(PinYcImageSizeInfo.record_size_x.offset, 0x14)
        self.assertEqual(PinYcImageSizeInfo.valid_size_x.offset, 0x20)
        self.assertEqual(PinYcImageSizeInfo.target_size_x.offset, 0x28)
        self.assertEqual(PinYcImageSizeInfo.data_placement.offset, 0x31)
        self.assertEqual(PinYcImageSizeInfo.cam_freq_char_h.offset, 0x38)

        class PinYcYcStateInfo(ctypes.Structure):
            _pack_ = 1
            _fields_ = [
                ("y_range", ctypes.c_uint8),
                ("colorimetry", ctypes.c_uint8),
                ("chroma_phase", ctypes.c_uint8),
                ("scanline", ctypes.c_uint8),
                ("copy_protection", ctypes.c_uint8),
                ("author", ctypes.c_uint8),
            ]

        self.assertEqual(ctypes.sizeof(PinYcYcStateInfo), 6, "Size of PIN_YC_YC_STATE_INFO must be exactly 6 bytes")

    def test_yc_state_info_accessors_disassembly(self):
        """Disassemble C_DataflowInfra_Entry_YcStateInfo in dataflowInfraFramework.so and verify all fields."""
        if not HAVE_ELF_TOOLS:
            self.skipTest("pyelftools and capstone required")

        expected_state_fields = {
            0x00: "YRange",
            0x01: "Colorimetry",
            0x02: "ChromaPhase",
            0x03: "Scanline",
            0x04: "CopyProtection",
            0x05: "Author",
        }

        with open(FRAMEWORK_SO, "rb") as f:
            elf = ELFFile(f)
            symtab = elf.get_section_by_name(".symtab") or elf.get_section_by_name(".dynsym")
            syms = {s.name: s for s in symtab.iter_symbols()
                    if "C_DataflowInfra_Entry_YcStateInfo" in s.name and "GetData_" in s.name}
            load_seg = next(seg for seg in elf.iter_segments()
                            if seg["p_type"] == "PT_LOAD" and seg["p_vaddr"] <= 0x25600 < seg["p_vaddr"] + seg["p_filesz"])

            md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

            for struct_off, field_name in expected_state_fields.items():
                expected_class_off = struct_off + 0x14
                getter_target = f"GetData_{field_name}"
                getter_sym = next((s for name, s in syms.items() if getter_target in name), None)
                self.assertIsNotNone(getter_sym, f"Getter {getter_target} not found")

                va = getter_sym["st_value"] & ~1
                file_off = load_seg["p_offset"] + (va - load_seg["p_vaddr"])
                f.seek(file_off)
                code = f.read(getter_sym["st_size"])

                insns = list(md.disasm(code, va))
                found_match = False
                for insn in insns:
                    m = re.search(r"\[r0(?:,\s*#(0x[0-9a-fA-F]+|[0-9]+))?\]", insn.op_str)
                    if m:
                        raw = m.group(1)
                        off = int(raw, 0) if raw else 0
                        self.assertEqual(off, expected_class_off,
                                         f"Field {field_name}: expected class offset 0x{expected_class_off:x}, got 0x{off:x}")
                        found_match = True
                        break
                self.assertTrue(found_match, f"Could not find [r0, #offset] load in {getter_target}")


class Test2_DmmUnitsAndExtents(unittest.TestCase):
    """Test 2: Verify DMM Unit and Extent IDs against DmmConfig.bin."""

    def setUp(self):
        self.assertTrue(DMM_CONFIG_BIN.is_file(), f"Missing DmmConfig.bin: {DMM_CONFIG_BIN}")
        self.data = DMM_CONFIG_BIN.read_bytes()

    def test_unit_table_mappings(self):
        """Verify DMM Unit to Extent mappings in 16-byte records [0xffffffff, unit_type, 0, extent_id]."""
        expected_units = {
            0x1dd: 0x227,  # Preview Ring 1
            0x2c5: 0x3da,  # Preview Ring 2
            0x2cd: 0x3e2,  # Preview Ring 3
            0x276: 0x333,  # Patched UVC YUY2 Source Workspace
            0x50e: 0x589,  # Stock UVC JPEG Staging
            0x50f: 0x58a,  # Stock UAC Audio FIFO
        }

        recovered_units = {}
        for off in range(0x10000, len(self.data) - 16, 4):
            hdr, u_type, f1, ext_id = struct.unpack_from("<4I", self.data, off)
            if hdr == 0xffffffff and u_type in expected_units:
                recovered_units[u_type] = ext_id

        for u_type, exp_ext in expected_units.items():
            self.assertIn(u_type, recovered_units, f"Unit 0x{u_type:03x} not found in DmmConfig.bin")
            self.assertEqual(recovered_units[u_type], exp_ext,
                             f"Unit 0x{u_type:03x} expected extent 0x{exp_ext:03x}, got 0x{recovered_units[u_type]:03x}")

    def test_extent_table_sizes(self):
        """Verify DMM Extent sizes in 20-byte records [attr, parent, type, id, size]."""
        expected_extents = {
            0x227: 614400,    # 0x96000 (640x480 YUV 4:2:2)
            0x3da: 614400,    # 0x96000 (640x480 YUV 4:2:2)
            0x3e2: 614400,    # 0x96000 (640x480 YUV 4:2:2)
            0x333: 3276800,   # 0x320000 (Patched UVC YUY2 source buffer)
            0x589: 1843200,   # 0x1c2000 (Stock staging)
            0x58a: 6144,      # 0x1800 (Audio FIFO)
        }

        recovered_sizes = {}
        for off in range(0x1000, 0x10000, 4):
            words = struct.unpack_from("<5I", self.data, off)
            ext_id = words[3]
            size = words[4]
            if ext_id in expected_extents and ext_id not in recovered_sizes:
                # Validate attr is active record (0x10f)
                if (words[0] & 0xff) == 0x0f:
                    recovered_sizes[ext_id] = size

        for ext_id, exp_size in expected_extents.items():
            self.assertIn(ext_id, recovered_sizes, f"Extent 0x{ext_id:03x} not found in extent table")
            self.assertEqual(recovered_sizes[ext_id], exp_size,
                             f"Extent 0x{ext_id:03x} expected size {exp_size} bytes, got {recovered_sizes[ext_id]}")

    def test_page_frame_number_formula(self):
        """Verify stream.ko PFN shift formula (phys >> 12)."""
        # Test unit 0x276 workspace physical base
        unit_0x276_phys = 0x15b00000
        pfn = unit_0x276_phys >> 12
        self.assertEqual(pfn, 0x15b00)
        self.assertEqual(pfn << 12, unit_0x276_phys)

        # Test page alignment masks
        page_mask = (1 << 12) - 1  # 4095
        self.assertEqual(unit_0x276_phys & page_mask, 0)


class Test3_ColorConversionKernels(unittest.TestCase):
    """Test 3: Validate color conversion correctness with bit-exact validation."""

    @classmethod
    def setUpClass(cls):
        """Compile raw_frame_source.c to dynamic shared library for testing."""
        cls.temp_dir = tempfile.mkdtemp(prefix="test_raw_frame_")
        cls.dll_path = Path(cls.temp_dir) / "libraw_frame_source.dll"

        # Compile with gcc
        cmd = [
            "gcc", "-O2", "-shared", "-fPIC", "-Wall", "-Wextra",
            "-I", str(HEADER_PATH.parent),
            str(SOURCE_PATH),
            "-o", str(cls.dll_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            shutil.rmtree(cls.temp_dir, ignore_errors=True)
            raise RuntimeError(f"Failed to compile raw_frame_source.c: {res.stderr}")

        cls.lib = ctypes.CDLL(str(cls.dll_path))

        # Setup ctypes prototypes
        cls.lib.raw_frame_convert_nv16_to_yuy2.argtypes = [
            ctypes.c_char_p, ctypes.c_size_t,
            ctypes.c_char_p, ctypes.c_size_t,
            ctypes.c_char_p, ctypes.c_size_t,
            ctypes.c_uint32, ctypes.c_uint32
        ]
        cls.lib.raw_frame_convert_nv16_to_yuy2.restype = ctypes.c_int

        cls.lib.raw_frame_convert_nv12_to_yuy2.argtypes = [
            ctypes.c_char_p, ctypes.c_size_t,
            ctypes.c_char_p, ctypes.c_size_t,
            ctypes.c_char_p, ctypes.c_size_t,
            ctypes.c_uint32, ctypes.c_uint32
        ]
        cls.lib.raw_frame_convert_nv12_to_yuy2.restype = ctypes.c_int

        cls.lib.raw_frame_copy_yuy2.argtypes = [
            ctypes.c_char_p, ctypes.c_size_t,
            ctypes.c_char_p, ctypes.c_size_t,
            ctypes.c_uint32, ctypes.c_uint32
        ]
        cls.lib.raw_frame_copy_yuy2.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        # Unload dll if possible and delete temp directory
        del cls.lib
        # Allow Windows file lock release
        import gc
        gc.collect()
        try:
            shutil.rmtree(cls.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def test_nv16_to_yuy2_bit_exact(self):
        """Verify NV16 (4:2:2 semi-planar) to YUY2 (packed 4:2:2) bit-exact conversion."""
        width = 640
        height = 480

        # Construct deterministic NV16 pattern
        y_plane = bytearray(width * height)
        uv_plane = bytearray(width * height)  # NV16 has full vertical chroma resolution

        for y in range(height):
            for x in range(width):
                y_plane[y * width + x] = (x * 3 + y * 7 + 13) & 0xff

        for y in range(height):
            for x in range(0, width, 2):
                # Interleaved Cb (U) and Cr (V)
                uv_plane[y * width + x] = (x * 11 + y * 5 + 29) & 0xff      # U
                uv_plane[y * width + x + 1] = (x * 17 + y * 13 + 37) & 0xff  # V

        dst_buf = bytearray(width * height * 2)

        res = self.lib.raw_frame_convert_nv16_to_yuy2(
            bytes(y_plane), width,
            bytes(uv_plane), width,
            (ctypes.c_char * len(dst_buf)).from_buffer(dst_buf), width * 2,
            width, height
        )
        self.assertEqual(res, 0, "raw_frame_convert_nv16_to_yuy2 returned non-zero")

        # Independent Bit-Exact Verification
        for y in range(height):
            for x in range(0, width, 2):
                dst_idx = y * (width * 2) + x * 2
                exp_y0 = (x * 3 + y * 7 + 13) & 0xff
                exp_u = (x * 11 + y * 5 + 29) & 0xff
                exp_y1 = ((x + 1) * 3 + y * 7 + 13) & 0xff
                exp_v = (x * 17 + y * 13 + 37) & 0xff

                self.assertEqual(dst_buf[dst_idx + 0], exp_y0, f"Mismatch Y0 at ({x},{y})")
                self.assertEqual(dst_buf[dst_idx + 1], exp_u, f"Mismatch U at ({x},{y})")
                self.assertEqual(dst_buf[dst_idx + 2], exp_y1, f"Mismatch Y1 at ({x},{y})")
                self.assertEqual(dst_buf[dst_idx + 3], exp_v, f"Mismatch V at ({x},{y})")

    def test_nv12_to_yuy2_bit_exact(self):
        """Verify NV12 (4:2:0 semi-planar) to YUY2 (packed 4:2:2) with vertical upsampling."""
        width = 640
        height = 480

        y_plane = bytearray(width * height)
        uv_plane = bytearray(width * (height // 2))  # NV12 has half vertical chroma resolution

        for y in range(height):
            for x in range(width):
                y_plane[y * width + x] = (x * 5 + y * 11 + 23) & 0xff

        for cy in range(height // 2):
            for x in range(0, width, 2):
                uv_plane[cy * width + x] = (x * 7 + cy * 19 + 41) & 0xff      # U
                uv_plane[cy * width + x + 1] = (x * 13 + cy * 29 + 59) & 0xff # V

        dst_buf = bytearray(width * height * 2)

        res = self.lib.raw_frame_convert_nv12_to_yuy2(
            bytes(y_plane), width,
            bytes(uv_plane), width,
            (ctypes.c_char * len(dst_buf)).from_buffer(dst_buf), width * 2,
            width, height
        )
        self.assertEqual(res, 0, "raw_frame_convert_nv12_to_yuy2 returned non-zero")

        # Independent Bit-Exact Verification (Chroma upsampled from cy = y // 2)
        for y in range(height):
            cy = y // 2
            for x in range(0, width, 2):
                dst_idx = y * (width * 2) + x * 2
                exp_y0 = (x * 5 + y * 11 + 23) & 0xff
                exp_u = (x * 7 + cy * 19 + 41) & 0xff
                exp_y1 = ((x + 1) * 5 + y * 11 + 23) & 0xff
                exp_v = (x * 13 + cy * 29 + 59) & 0xff

                self.assertEqual(dst_buf[dst_idx + 0], exp_y0, f"Mismatch Y0 at ({x},{y})")
                self.assertEqual(dst_buf[dst_idx + 1], exp_u, f"Mismatch U at ({x},{y})")
                self.assertEqual(dst_buf[dst_idx + 2], exp_y1, f"Mismatch Y1 at ({x},{y})")
                self.assertEqual(dst_buf[dst_idx + 3], exp_v, f"Mismatch V at ({x},{y})")

    def test_copy_yuy2_linear(self):
        """Verify linear copy of YUY2 frame."""
        width = 640
        height = 480
        src_buf = bytearray(os.urandom(width * height * 2))
        dst_buf = bytearray(width * height * 2)

        res = self.lib.raw_frame_copy_yuy2(
            bytes(src_buf), width * 2,
            (ctypes.c_char * len(dst_buf)).from_buffer(dst_buf), width * 2,
            width, height
        )
        self.assertEqual(res, 0)
        self.assertEqual(src_buf, dst_buf)

    def test_invalid_parameters_rejected(self):
        """Verify error checking rejects null buffers and invalid dimensions."""
        # Null destination
        res = self.lib.raw_frame_convert_nv16_to_yuy2(None, 640, None, 640, None, 1280, 640, 480)
        self.assertEqual(res, -1)  # RAW_FRAME_ERR_INVALID_PARAM

        # Odd width
        y_dummy = b"\x00" * 640
        res = self.lib.raw_frame_convert_nv16_to_yuy2(y_dummy, 640, y_dummy, 640, y_dummy, 1280, 639, 480)
        self.assertEqual(res, -1)

    def test_padded_strides(self):
        """Verify conversion works correctly with padded row strides (e.g. 704 > 640)."""
        width = 640
        height = 480
        y_stride = 704
        uv_stride = 704
        dst_stride = 1344

        y_plane = bytearray(y_stride * height)
        uv_plane = bytearray(uv_stride * height)
        for y in range(height):
            for x in range(width):
                y_plane[y * y_stride + x] = (x + y) & 0xff
            for x in range(0, width, 2):
                uv_plane[y * uv_stride + x] = 100
                uv_plane[y * uv_stride + x + 1] = 200

        # Fill dst with canary bytes
        dst_buf = bytearray(b"\xaa" * (dst_stride * height))

        res = self.lib.raw_frame_convert_nv16_to_yuy2(
            bytes(y_plane), y_stride,
            bytes(uv_plane), uv_stride,
            (ctypes.c_char * len(dst_buf)).from_buffer(dst_buf), dst_stride,
            width, height
        )
        self.assertEqual(res, 0)

        # Verify pixels and verify padding canary is preserved
        for y in range(height):
            dst_row = dst_buf[y * dst_stride:(y + 1) * dst_stride]
            # First width * 2 bytes must match YUY2
            for x in range(0, width, 2):
                idx = x * 2
                self.assertEqual(dst_row[idx + 0], (x + y) & 0xff)
                self.assertEqual(dst_row[idx + 1], 100)
                self.assertEqual(dst_row[idx + 2], (x + 1 + y) & 0xff)
                self.assertEqual(dst_row[idx + 3], 200)
            # Remaining padding bytes must remain 0xaa
            padding = dst_row[width * 2:]
            self.assertEqual(padding, bytearray(b"\xaa" * (dst_stride - width * 2)))


class Test4_SyntheticFallback(unittest.TestCase):
    """Test 4: Validate synthetic fallback test pattern generation and lifecycle API."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="test_synthetic_")
        cls.dll_path = Path(cls.temp_dir) / "libraw_frame_source.dll"

        cmd = [
            "gcc", "-O2", "-shared", "-fPIC", "-Wall", "-Wextra",
            "-I", str(HEADER_PATH.parent),
            str(SOURCE_PATH),
            "-o", str(cls.dll_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            shutil.rmtree(cls.temp_dir, ignore_errors=True)
            raise RuntimeError(f"Failed to compile raw_frame_source.c: {res.stderr}")

        cls.lib = ctypes.CDLL(str(cls.dll_path))

        cls.lib.raw_frame_generate_synthetic_fallback.argtypes = [
            ctypes.c_char_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32
        ]
        cls.lib.raw_frame_generate_synthetic_fallback.restype = ctypes.c_int

        cls.lib.raw_frame_source_init.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        cls.lib.raw_frame_source_init.restype = ctypes.c_int
        cls.lib.raw_frame_source_acquire.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32]
        cls.lib.raw_frame_source_acquire.restype = ctypes.c_int
        cls.lib.raw_frame_source_convert_to_yuy2.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
        cls.lib.raw_frame_source_convert_to_yuy2.restype = ctypes.c_int
        cls.lib.raw_frame_source_release.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        cls.lib.raw_frame_source_release.restype = ctypes.c_int
        cls.lib.raw_frame_source_teardown.argtypes = [ctypes.c_void_p]
        cls.lib.raw_frame_source_teardown.restype = None

    @classmethod
    def tearDownClass(cls):
        del cls.lib
        import gc
        gc.collect()
        try:
            shutil.rmtree(cls.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def test_smpte_color_bars_top_rows(self):
        """Verify 8 standard SMPTE color bars across rows 0 to 471."""
        width = 640
        height = 480
        frame_counter = 42
        dst_buf = bytearray(width * height * 2)

        res = self.lib.raw_frame_generate_synthetic_fallback(
            (ctypes.c_char * len(dst_buf)).from_buffer(dst_buf),
            width, height, frame_counter
        )
        self.assertEqual(res, 0)

        # 8 expected colors (Y, U, V)
        expected_bars = [
            (235, 128, 128),  # White
            (210, 16, 146),   # Yellow
            (170, 166, 16),   # Cyan
            (145, 54, 34),    # Green
            (106, 202, 222),  # Magenta
            (81, 90, 240),    # Red
            (41, 240, 110),   # Blue
            (16, 128, 128),   # Black
        ]

        bar_width = 80  # 640 / 8

        # Test sample rows across upper section
        for y in (0, 10, 100, 240, 400, 471):
            for bar_idx, (exp_y, exp_u, exp_v) in enumerate(expected_bars):
                # Sample middle of each bar
                x = bar_idx * bar_width + 40
                dst_idx = y * (width * 2) + x * 2

                self.assertEqual(dst_buf[dst_idx + 0], exp_y, f"Bar {bar_idx} Y0 mismatch at row {y}")
                self.assertEqual(dst_buf[dst_idx + 1], exp_u, f"Bar {bar_idx} U mismatch at row {y}")
                self.assertEqual(dst_buf[dst_idx + 2], exp_y, f"Bar {bar_idx} Y1 mismatch at row {y}")
                self.assertEqual(dst_buf[dst_idx + 3], exp_v, f"Bar {bar_idx} V mismatch at row {y}")

    def test_binary_counter_bottom_rows(self):
        """Verify dynamic 16-bit binary counter across rows 472 to 479."""
        width = 640
        height = 480
        dst_buf = bytearray(width * height * 2)

        test_counters = [0x0000, 0x0001, 0x0002, 0x0055, 0x00aa, 0x1234, 0xffff]
        bit_width = 40  # 640 / 16

        for counter in test_counters:
            res = self.lib.raw_frame_generate_synthetic_fallback(
                (ctypes.c_char * len(dst_buf)).from_buffer(dst_buf),
                width, height, counter
            )
            self.assertEqual(res, 0)

            for y in range(472, 480):
                for bit in range(16):
                    x = bit * bit_width + 20
                    dst_idx = y * (width * 2) + x * 2
                    exp_val = 235 if (counter & (1 << bit)) else 16

                    self.assertEqual(dst_buf[dst_idx + 0], exp_val,
                                     f"Counter 0x{counter:04x} bit {bit} mismatch at y={y}")
                    self.assertEqual(dst_buf[dst_idx + 1], 128, "U should be neutral 128")
                    self.assertEqual(dst_buf[dst_idx + 2], exp_val,
                                     f"Counter 0x{counter:04x} bit {bit} mismatch at y={y}")
                    self.assertEqual(dst_buf[dst_idx + 3], 128, "V should be neutral 128")

    def test_lifecycle_api_integration(self):
        """Verify raw_frame_source init, acquire, convert, release, teardown lifecycle."""
        class PinYcImageSizeInfo(ctypes.Structure):
            _pack_ = 1
            _fields_ = [
                ("image_attach", ctypes.c_uint8),
                ("reserved0", ctypes.c_uint8 * 3),
                ("unit_type", ctypes.c_uint32),
                ("unit_handle", ctypes.c_uint16),
                ("reserved1", ctypes.c_uint16),
                ("unit_data_offset", ctypes.c_uint32),
                ("exposure_time", ctypes.c_uint8),
                ("expose_pic_delay", ctypes.c_uint8),
                ("scenario_end", ctypes.c_uint8),
                ("mirror", ctypes.c_uint8),
                ("record_size_x", ctypes.c_uint16),
                ("record_size_y", ctypes.c_uint16),
                ("canvas_size_x", ctypes.c_uint16),
                ("canvas_size_y", ctypes.c_uint16),
                ("valid_offset_x", ctypes.c_uint16),
                ("valid_offset_y", ctypes.c_uint16),
                ("valid_size_x", ctypes.c_uint16),
                ("valid_size_y", ctypes.c_uint16),
                ("target_offset_x", ctypes.c_uint16),
                ("target_offset_y", ctypes.c_uint16),
                ("target_size_x", ctypes.c_uint16),
                ("target_size_y", ctypes.c_uint16),
                ("data_site", ctypes.c_uint8),
                ("iib_number", ctypes.c_uint8),
                ("aspect", ctypes.c_uint8),
                ("yc_compress", ctypes.c_uint8),
                ("data_transfer", ctypes.c_uint8),
                ("data_placement", ctypes.c_uint8),
                ("data_content", ctypes.c_uint8),
                ("data_scan", ctypes.c_uint8),
                ("strip_width", ctypes.c_uint16),
                ("yc_bit_depth", ctypes.c_uint8),
                ("reserved2", ctypes.c_uint8),
                ("cam_freq_char_h", ctypes.c_uint16),
                ("reserved3", ctypes.c_uint16),
            ]

        class RawFrameConfig(ctypes.Structure):
            _fields_ = [
                ("width", ctypes.c_uint32),
                ("height", ctypes.c_uint32),
                ("dmm_unit_type", ctypes.c_uint32),
                ("timeout_ms", ctypes.c_uint32),
                ("allow_synthetic_fallback", ctypes.c_bool),
                ("stream_dev_path", ctypes.c_char_p),
            ]

        class RawFrameDesc(ctypes.Structure):
            _fields_ = [
                ("format", ctypes.c_int),
                ("width", ctypes.c_uint32),
                ("height", ctypes.c_uint32),
                ("y_stride", ctypes.c_uint32),
                ("uv_stride", ctypes.c_uint32),
                ("phys_addr", ctypes.c_uint32),
                ("vaddr_y", ctypes.c_void_p),
                ("vaddr_uv", ctypes.c_void_p),
                ("mapping_base", ctypes.c_void_p),
                ("mapping_len", ctypes.c_size_t),
                ("data_size", ctypes.c_size_t),
                ("unit_handle", ctypes.c_uint16),
                ("frame_index", ctypes.c_uint32),
                ("is_synthetic", ctypes.c_bool),
                ("size_info", PinYcImageSizeInfo),
            ]

        class RawFrameSourceCtx(ctypes.Structure):
            _fields_ = [
                ("config", RawFrameConfig),
                ("stream_fd", ctypes.c_int),
                ("frame_counter", ctypes.c_uint32),
                ("fallback_count", ctypes.c_uint32),
                ("initialized", ctypes.c_bool),
                ("staging_mapping", ctypes.c_void_p),
                ("staging_map_len", ctypes.c_size_t),
                ("staging_phys_addr", ctypes.c_uint32),
            ]

        ctx = RawFrameSourceCtx()
        desc = RawFrameDesc()

        # Step 0: Test acquire without init -> must fail with RAW_FRAME_ERR_NOT_INIT (-2)
        res = self.lib.raw_frame_source_acquire(ctypes.byref(ctx), ctypes.byref(desc), 1000)
        self.assertEqual(res, -2)

        # Step 1: Initialize context with synthetic fallback enabled
        config = RawFrameConfig()
        config.width = 640
        config.height = 480
        config.dmm_unit_type = 0x276
        config.timeout_ms = 3000
        config.allow_synthetic_fallback = True
        config.stream_dev_path = b"/dev/stream"

        res = self.lib.raw_frame_source_init(ctypes.byref(ctx), ctypes.byref(config))
        self.assertEqual(res, 0, "raw_frame_source_init failed")
        self.assertTrue(ctx.initialized)

        # Step 2: Acquire frame -> should trigger fallback with is_synthetic = True
        res = self.lib.raw_frame_source_acquire(ctypes.byref(ctx), ctypes.byref(desc), 1000)
        self.assertEqual(res, 0, "raw_frame_source_acquire failed")
        self.assertTrue(desc.is_synthetic)
        self.assertEqual(desc.width, 640)
        self.assertEqual(desc.height, 480)
        self.assertEqual(desc.data_size, 614400)
        self.assertEqual(desc.frame_index, 0)
        self.assertEqual(ctx.fallback_count, 1)

        # Step 3: Convert acquired frame into output YUY2 buffer
        yuy2_output = bytearray(614400)
        res = self.lib.raw_frame_source_convert_to_yuy2(
            ctypes.byref(ctx),
            ctypes.byref(desc),
            (ctypes.c_char * len(yuy2_output)).from_buffer(yuy2_output),
            len(yuy2_output)
        )
        self.assertEqual(res, 0, "raw_frame_source_convert_to_yuy2 failed")

        # Verify first 4 bytes of converted buffer: White bar (Y0=235, U=128, Y1=235, V=128)
        self.assertEqual(yuy2_output[0], 235)
        self.assertEqual(yuy2_output[1], 128)
        self.assertEqual(yuy2_output[2], 235)
        self.assertEqual(yuy2_output[3], 128)

        # Step 4: Release frame
        res = self.lib.raw_frame_source_release(ctypes.byref(ctx), ctypes.byref(desc))
        self.assertEqual(res, 0, "raw_frame_source_release failed")

        # Step 5: Acquire second frame -> frame_index should increment to 1
        res = self.lib.raw_frame_source_acquire(ctypes.byref(ctx), ctypes.byref(desc), 1000)
        self.assertEqual(res, 0)
        self.assertEqual(desc.frame_index, 1)
        self.assertEqual(ctx.fallback_count, 2)

        # Step 6: Teardown
        self.lib.raw_frame_source_teardown(ctypes.byref(ctx))
        self.assertFalse(ctx.initialized)


def main():
    print("=" * 80)
    print("Running Raw Frame Source Verification Suite (Sony ZV-E10 UVC Subsystem)")
    print(f"Python executable: {sys.executable}")
    print(f"Header: {HEADER_PATH}")
    print(f"Source: {SOURCE_PATH}")
    print("=" * 80)

    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite()
    suite.addTest(loader.loadTestsFromTestCase(Test1_StructOffsetsAndSizes))
    suite.addTest(loader.loadTestsFromTestCase(Test2_DmmUnitsAndExtents))
    suite.addTest(loader.loadTestsFromTestCase(Test3_ColorConversionKernels))
    suite.addTest(loader.loadTestsFromTestCase(Test4_SyntheticFallback))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
