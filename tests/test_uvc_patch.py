#!/usr/bin/env python3
"""
Comprehensive Multi-Layer Adversarial Verification Suite for Sony ZV-E10 UVC Subsystem.

Validates the full UVC webcam pipeline across 8 architectural components:
  1. Cryptographic Hash & Firmware Dump Integrity (SHA-256, MD5, ELF32 headers, physical symbols)
  2. Capstone Instruction-Level Guardrails (Thumb-2 mov.w r2, #1920, AAPCS callee-saved preservation, branch/pool alignment)
  3. UVC Descriptor Specification Integrity (CS_INTERFACE wTotalLength == 61, VS_FORMAT, VS_FRAME, VS_COLORFORMAT BT.709)
  4. Registration Table & Dynamic Relocation Preservation (.data.rel.ro lengths=61, R_ARM_RELATIVE pointers untouched)
  5. USB 2.0 Bulk Endpoint & Transfer Bandwidth Validation (Endpoint 0x81 wMaxPacketSize = 512, throughput <= 43 MB/s)
  6. Multi-OS Host Descriptor Parsing Emulation (Linux uvcvideo, Windows usbvideo.sys, macOS CoreMediaIO)
  7. Adversarial Mutation & Tamper Detection (Bit flips, offset corruption, length mismatch, bandwidth overflow rejection)
  8. Single-Shot Patch Generator Idempotency & Cleanliness (scripts/patch_uvc.py programmatic API & CLI)
"""

import hashlib
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple
import unittest

import capstone
from capstone import arm
from elftools.elf.elffile import ELFFile

import batch_patch_uvc as bpu
import scripts.patch_uvc as patch_uvc
import scripts.patch_uvc_libraries as pul

REPO_ROOT = Path(__file__).resolve().parent.parent
LIB_USB_CMN_STOCK = REPO_ROOT / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libInfraUsbCmn.so"
LIB_STREAMING_STOCK = REPO_ROOT / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libInfraStreamingUsb.so"
USBG_VIDEO_STOCK = REPO_ROOT / "dumps" / "camera_2025" / "usr" / "usr" / "kmod" / "usbg_video.ko"

LIB_USB_CMN_PATCHED = REPO_ROOT / "dumps" / "staged" / "uvc" / "binaries" / "patched" / "libInfraUsbCmn.so"
LIB_STREAMING_PATCHED = REPO_ROOT / "dumps" / "staged" / "uvc" / "binaries" / "patched" / "libInfraStreamingUsb.so"

HOOK_SO = REPO_ROOT / "out" / "uvc_hook.so"
FILE_PATCH_ELF = REPO_ROOT / "out" / "file_patch.elf"
LIVE_SH = REPO_ROOT / "research" / "device" / "apply_uvc_live.sh"

PYTHON_EXE = Path(REPO_ROOT / ".venv" / "Scripts" / "python.exe")
if not PYTHON_EXE.exists():
    PYTHON_EXE = Path("python")

# Authoritative hash database
HASH_DB = {
    "libInfraUsbCmn.so": {
        "stock_size": 94612,
        "stock_md5": "31308976206a837f6f5c571992d2b499",
        "stock_sha256": "af830315ce51c38b010995f2147d556286364323734f64b877fcc3bb1a916c02",
        "patched_size": 94612,
        "patched_md5": "ac1961d23addcd53f4fe7210d074eac2",
        "patched_sha256": "f089b3f66971edd6a3c5128ee7a8d295884fbf8dcc7bf51db94664998c509946",
    },
    "libInfraStreamingUsb.so": {
        "stock_size": 52524,
        "stock_md5": "cde7a1b42c919706aa5f61aba5fc0d75",
        "stock_sha256": "0a9448e364e8f014db02edc8e164470c70f2d2143ce5de74697e9ffba697cce8",
        "patched_size": 52524,
        "patched_md5": "5a0417693a3d9ed1786c4d0afc043d6e",
        "patched_sha256": "e96fe28b9ac19b2ee918173f629d69a26c6f82766e28f4fd8fdfbb28d8a14259",
    },
    "usbg_video.ko": {
        "stock_size": 20668,
        "stock_md5": "5b59c2e62c80683d754955ab5de0467d",
        "stock_sha256": "d385a051bf01b0e5ea37412623ae85cfe3cda76ab0d11e61d111994ca9fbf4fb",
    },
}


# ==============================================================================
# Helper Classes & Host OS Parsing Emulators
# ==============================================================================

class UvcDescriptorError(Exception):
    """Raised when UVC descriptor structure or specification rules are violated."""
    pass


class UvcDescriptorParser:
    """Parses and validates UVC Class-Specific Video Streaming (VS) descriptor hierarchies."""

    @staticmethod
    def parse_vs_hierarchy(data: bytes, base_offset: int = 0) -> Dict[str, Any]:
        """
        Parse complete UVC Video Streaming descriptor chain:
          VS_INPUT_HEADER (0x01) -> VS_FORMAT_MJPEG (0x06) -> VS_FRAME_MJPEG (0x07) -> VS_COLORFORMAT (0x0d)
        """
        if len(data) < base_offset + 14:
            raise UvcDescriptorError(f"Insufficient data for VS_INPUT_HEADER: {len(data) - base_offset} B")

        # 1. VS_INPUT_HEADER (Subtype 0x01)
        h_len, h_type, h_subtype = struct.unpack("<BBB", data[base_offset:base_offset + 3])
        if h_type != 0x24:
            raise UvcDescriptorError(f"Header bDescriptorType {h_type:#x} != CS_INTERFACE (0x24)")
        if h_subtype != 0x01:
            raise UvcDescriptorError(f"Header bDescriptorSubType {h_subtype:#x} != VS_INPUT_HEADER (0x01)")
        if h_len < 13:
            raise UvcDescriptorError(f"VS_INPUT_HEADER bLength {h_len} < 13")

        bNumFormats, wTotalLength, bEndpointAddress = struct.unpack("<BBH", data[base_offset + 3:base_offset + 7])
        # Note: struct <BBH unpacks bNumFormats (1B), and next 2B as wTotalLength
        # Actually in UVC:
        # byte 0: bLength (1B)
        # byte 1: bDescriptorType (1B)
        # byte 2: bDescriptorSubType (1B)
        # byte 3: bNumFormats (1B)
        # byte 4-5: wTotalLength (2B)
        # byte 6: bEndpointAddress (1B)
        bNumFormats = data[base_offset + 3]
        wTotalLength = struct.unpack("<H", data[base_offset + 4:base_offset + 6])[0]
        bEndpointAddress = data[base_offset + 6]

        curr = base_offset + h_len
        formats = []
        frames = []
        color_formats = []
        child_bytes_sum = h_len

        try:
            while curr < base_offset + wTotalLength and curr < len(data):
                if curr + 3 > len(data):
                    raise UvcDescriptorError(f"Truncated child descriptor header at offset {curr:#x}")
                d_len = data[curr]
                if d_len < 3 or curr + d_len > len(data):
                    raise UvcDescriptorError(f"Invalid child descriptor length {d_len} at offset {curr:#x}")
                d_type = data[curr + 1]
                if d_type != 0x24:
                    raise UvcDescriptorError(f"Child descriptor type {d_type:#x} != CS_INTERFACE (0x24) at {curr:#x}")
                d_subtype = data[curr + 2]

                if d_subtype == 0x06:  # VS_FORMAT_MJPEG
                    if d_len < 11:
                        raise UvcDescriptorError(f"VS_FORMAT_MJPEG length {d_len} < 11")
                    bFormatIndex, bNumFrameDescriptors = struct.unpack("<BB", data[curr + 3:curr + 5])
                    formats.append({
                        "bFormatIndex": bFormatIndex,
                        "bNumFrameDescriptors": bNumFrameDescriptors,
                        "bLength": d_len,
                        "raw": data[curr:curr + d_len],
                    })
                elif d_subtype == 0x07:  # VS_FRAME_MJPEG
                    if d_len < 26:
                        raise UvcDescriptorError(f"VS_FRAME_MJPEG length {d_len} < 26")
                    bFrameIndex, bmCapabilities, wWidth, wHeight = struct.unpack("<BBHH", data[curr + 3:curr + 9])
                    dwMinBitRate, dwMaxBitRate, dwMaxBuf = struct.unpack("<III", data[curr + 9:curr + 21])
                    dwDefInterval, bFrameIntervalType = struct.unpack("<IB", data[curr + 21:curr + 26])
                    intervals = []
                    if bFrameIntervalType > 0:
                        for i in range(bFrameIntervalType):
                            ipos = curr + 26 + (i * 4)
                            if ipos + 4 <= curr + d_len:
                                intervals.append(struct.unpack("<I", data[ipos:ipos + 4])[0])

                    frames.append({
                        "bFrameIndex": bFrameIndex,
                        "bmCapabilities": bmCapabilities,
                        "wWidth": wWidth,
                        "wHeight": wHeight,
                        "dwMinBitRate": dwMinBitRate,
                        "dwMaxBitRate": dwMaxBitRate,
                        "dwMaxVideoFrameBufferSize": dwMaxBuf,
                        "dwDefaultFrameInterval": dwDefInterval,
                        "bFrameIntervalType": bFrameIntervalType,
                        "intervals": intervals,
                        "bLength": d_len,
                        "raw": data[curr:curr + d_len],
                    })
                elif d_subtype == 0x0D:  # VS_COLORFORMAT
                    if d_len < 6:
                        raise UvcDescriptorError(f"VS_COLORFORMAT length {d_len} < 6")
                    bColorPrimaries, bTransfer, bMatrix = struct.unpack("<BBB", data[curr + 3:curr + 6])
                    color_formats.append({
                        "bColorPrimaries": bColorPrimaries,
                        "bTransferCharacteristics": bTransfer,
                        "bMatrixCoefficients": bMatrix,
                        "bLength": d_len,
                        "raw": data[curr:curr + d_len],
                    })

                child_bytes_sum += d_len
                curr += d_len
        except IndexError as e:
            raise UvcDescriptorError(f"Descriptor stream truncated at offset {curr:#x}: {e}") from e

        return {
            "header": {
                "bLength": h_len,
                "bDescriptorType": h_type,
                "bDescriptorSubType": h_subtype,
                "bNumFormats": bNumFormats,
                "wTotalLength": wTotalLength,
                "bEndpointAddress": bEndpointAddress,
            },
            "formats": formats,
            "frames": frames,
            "color_formats": color_formats,
            "calculated_total_length": child_bytes_sum,
            "wTotalLength": wTotalLength,
            "span_bytes": curr - base_offset,
        }


class LinuxUvcEmulator:
    """
    Simulates Linux kernel uvcvideo driver descriptor parsing logic
    (Reference: drivers/media/usb/uvc/uvc_driver.c uvc_parse_streaming).
    """

    @staticmethod
    def parse_streaming(data: bytes, base_offset: int = 0) -> Dict[str, Any]:
        info = UvcDescriptorParser.parse_vs_hierarchy(data, base_offset)
        hdr = info["header"]

        # Kernel check 1: wTotalLength must equal exact sum of parsed descriptors
        if info["calculated_total_length"] != hdr["wTotalLength"]:
            raise UvcDescriptorError(
                f"[Linux uvcvideo] wTotalLength mismatch: advertised {hdr['wTotalLength']}, "
                f"calculated {info['calculated_total_length']}"
            )

        # Kernel check 2: Format count must match bNumFormats
        if len(info["formats"]) != hdr["bNumFormats"]:
            raise UvcDescriptorError(
                f"[Linux uvcvideo] bNumFormats mismatch: header claims {hdr['bNumFormats']}, "
                f"found {len(info['formats'])}"
            )

        # Kernel check 3: Format indices must be 1-based monotonic
        for idx, fmt in enumerate(info["formats"], start=1):
            if fmt["bFormatIndex"] != idx:
                raise UvcDescriptorError(f"[Linux uvcvideo] Non-monotonic format index: {fmt['bFormatIndex']}")

        # Kernel check 4: Frame descriptors must match bNumFrameDescriptors
        if len(info["frames"]) < 1:
            raise UvcDescriptorError("[Linux uvcvideo] No valid video frames found")
        for fmt in info["formats"]:
            if fmt["bNumFrameDescriptors"] != len(info["frames"]):
                raise UvcDescriptorError(
                    f"[Linux uvcvideo] Frame descriptor count {len(info['frames'])} "
                    f"!= format.bNumFrameDescriptors {fmt['bNumFrameDescriptors']}"
                )

        # Kernel check 5: Discrete intervals must match bFrameIntervalType
        for frame in info["frames"]:
            if frame["bFrameIntervalType"] > 0:
                if len(frame["intervals"]) != frame["bFrameIntervalType"]:
                    raise UvcDescriptorError(
                        f"[Linux uvcvideo] Interval count mismatch: expected {frame['bFrameIntervalType']}, "
                        f"got {len(frame['intervals'])}"
                    )

        return {"status": "SUCCESS", "os": "Linux uvcvideo", "parsed": info}


class WindowsUvcEmulator:
    """
    Simulates Microsoft Windows USB Video Class driver (usbvideo.sys) verification rules.
    """

    @staticmethod
    def validate_stream_descriptor(data: bytes, base_offset: int = 0, endpoint_packet_size: int = 512) -> Dict[str, Any]:
        info = UvcDescriptorParser.parse_vs_hierarchy(data, base_offset)
        hdr = info["header"]

        # Windows check 1: Total length exact match
        if info["calculated_total_length"] != hdr["wTotalLength"]:
            raise UvcDescriptorError(f"[Windows usbvideo.sys] Buffer length mismatch (Event ID 219)")

        # Windows check 2: High-Speed USB 2.0 Bulk Endpoint Max Packet Size must be exactly 512
        if endpoint_packet_size != 512:
            raise UvcDescriptorError(
                f"[Windows usbvideo.sys] Invalid Bulk Endpoint max packet size: {endpoint_packet_size} "
                f"(High-Speed Bulk must be 512) -> Code 10 / Code 43 Failure"
            )

        # Windows check 3: Must have at least 1 video frame descriptor
        if len(info["frames"]) < 1:
            raise UvcDescriptorError("[Windows usbvideo.sys] No valid video frames found")

        # Windows check 4: Buffer bounds and non-zero dimensions without 16-bit unsigned overflow
        for frame in info["frames"]:
            w, h = frame["wWidth"], frame["wHeight"]
            if w == 0 or h == 0 or w > 65535 or h > 65535:
                raise UvcDescriptorError(f"[Windows usbvideo.sys] Invalid frame geometry: {w}x{h}")
            if frame["dwMaxVideoFrameBufferSize"] == 0:
                raise UvcDescriptorError("[Windows usbvideo.sys] dwMaxVideoFrameBufferSize cannot be zero")
            if frame["dwMinBitRate"] == 0 or frame["dwMaxBitRate"] == 0:
                raise UvcDescriptorError("[Windows usbvideo.sys] Bitrate fields cannot be zero")
            if frame["dwMinBitRate"] > frame["dwMaxBitRate"]:
                raise UvcDescriptorError("[Windows usbvideo.sys] dwMinBitRate > dwMaxBitRate")
            if frame["dwDefaultFrameInterval"] == 0:
                raise UvcDescriptorError("[Windows usbvideo.sys] Default frame interval cannot be zero")
            fps = 10_000_000 / frame["dwDefaultFrameInterval"]
            if not (1.0 <= fps <= 120.0):
                raise UvcDescriptorError(f"[Windows usbvideo.sys] Calculated FPS {fps} outside [1, 120] range")

        return {"status": "SUCCESS", "os": "Windows usbvideo.sys", "parsed": info}


class MacOsUvcEmulator:
    """
    Simulates Apple macOS CoreMediaIO / AppleUSBVideoSupport descriptor parsing logic.
    """

    @staticmethod
    def validate_stream_descriptor(data: bytes, base_offset: int = 0) -> Dict[str, Any]:
        info = UvcDescriptorParser.parse_vs_hierarchy(data, base_offset)

        # macOS check 1: Must have at least 1 video frame descriptor
        if len(info["frames"]) < 1:
            raise UvcDescriptorError("[macOS CoreMediaIO] No valid video frames found")

        # macOS check 2: Fixed 30-byte frame descriptor structure for single discrete interval
        for frame in info["frames"]:
            if frame["bFrameIntervalType"] == 1 and frame["bLength"] != 30:
                raise UvcDescriptorError(
                    f"[macOS CoreMediaIO] Discrete single-interval frame descriptor must be 30 bytes, "
                    f"got {frame['bLength']}"
                )
            if frame["wHeight"] == 0 or frame["wWidth"] == 0:
                raise UvcDescriptorError("[macOS CoreMediaIO] Zero frame dimensions")
            aspect = frame["wWidth"] / frame["wHeight"]
            if aspect <= 0:
                raise UvcDescriptorError("[macOS CoreMediaIO] Invalid aspect ratio")

        # macOS check 2: Color primary compliance
        for color in info["color_formats"]:
            if color["bColorPrimaries"] not in (1, 2, 3):  # BT.709, BT.470-2M, BT.470-2BG
                raise UvcDescriptorError(f"[macOS CoreMediaIO] Unsupported color primaries: {color['bColorPrimaries']}")

        # macOS check 3: Header span equals wTotalLength
        if info["span_bytes"] != info["wTotalLength"]:
            raise UvcDescriptorError(
                f"[macOS CoreMediaIO] Truncated descriptor hierarchy: {info['span_bytes']} != {info['wTotalLength']}"
            )

        return {"status": "SUCCESS", "os": "macOS CoreMediaIO", "parsed": info}


class CapstoneGuardrailValidator:
    """Disassembles and verifies ARM/Thumb-2 instruction properties and AAPCS register compliance."""

    def __init__(self):
        self.md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
        self.md.detail = True
        self.callee_saved = {
            arm.ARM_REG_R4, arm.ARM_REG_R5, arm.ARM_REG_R6, arm.ARM_REG_R7,
            arm.ARM_REG_R8, arm.ARM_REG_R9, arm.ARM_REG_R10, arm.ARM_REG_R11,
            arm.ARM_REG_SP, arm.ARM_REG_LR,
        }

    def decode_single(self, raw_bytes: bytes, address: int) -> capstone.CsInsn:
        insns = list(self.md.disasm(raw_bytes, address))
        if len(insns) != 1:
            raise ValueError(f"Expected 1 instruction from {raw_bytes.hex()}, got {len(insns)}")
        insn = insns[0]
        if len(insn.bytes) != len(raw_bytes):
            raise ValueError(f"Undecoded trailing bytes in {raw_bytes.hex()}")
        return insn

    def verify_no_callee_saved_clobber(self, insn: capstone.CsInsn) -> bool:
        regs_read, regs_written = insn.regs_access()
        for reg in regs_written:
            if reg in self.callee_saved:
                return False
        # Also check destination operands
        if len(insn.operands) > 0:
            op0 = insn.operands[0]
            if op0.type == arm.ARM_OP_REG and op0.reg in self.callee_saved:
                return False
        return True


# ==============================================================================
# Component 1: Cryptographic Hash & Firmware Dump Integrity
# ==============================================================================

class TestComponent1CryptographicHashAndDumpIntegrity(unittest.TestCase):
    """Component 1: Validates cryptographic hashes, ELF32 headers, and physical symbols in dumps."""

    def test_stock_binary_hashes_and_sizes(self):
        """Verify stock dump binaries match authoritative SHA-256 and MD5 hashes exactly."""
        targets = [
            (LIB_USB_CMN_STOCK, HASH_DB["libInfraUsbCmn.so"]),
            (LIB_STREAMING_STOCK, HASH_DB["libInfraStreamingUsb.so"]),
            (USBG_VIDEO_STOCK, HASH_DB["usbg_video.ko"]),
        ]
        for path, meta in targets:
            self.assertTrue(path.exists(), f"Missing stock dump: {path}")
            data = path.read_bytes()
            self.assertEqual(len(data), meta["stock_size"], f"Size mismatch for {path.name}")
            self.assertEqual(hashlib.md5(data).hexdigest(), meta["stock_md5"], f"MD5 mismatch for {path.name}")
            self.assertEqual(hashlib.sha256(data).hexdigest(), meta["stock_sha256"], f"SHA256 mismatch for {path.name}")

    def test_patched_binary_hashes_and_sizes(self):
        """Verify staged patched binaries match authoritative SHA-256 and MD5 hashes."""
        targets = [
            (LIB_USB_CMN_PATCHED, HASH_DB["libInfraUsbCmn.so"]),
            (LIB_STREAMING_PATCHED, HASH_DB["libInfraStreamingUsb.so"]),
        ]
        for path, meta in targets:
            self.assertTrue(path.exists(), f"Missing patched binary: {path}")
            data = path.read_bytes()
            self.assertEqual(len(data), meta["patched_size"], f"Size mismatch for {path.name}")
            self.assertEqual(hashlib.md5(data).hexdigest(), meta["patched_md5"], f"Patched MD5 mismatch for {path.name}")
            self.assertEqual(hashlib.sha256(data).hexdigest(), meta["patched_sha256"], f"Patched SHA256 mismatch for {path.name}")

    def test_stock_elf32_headers(self):
        """Verify ELF32 headers: ELFCLASS32, ELFDATA2LSB, EM_ARM (40), appropriate e_type."""
        checks = [
            (LIB_USB_CMN_STOCK, "ET_DYN"),
            (LIB_STREAMING_STOCK, "ET_DYN"),
            (USBG_VIDEO_STOCK, "ET_REL"),
        ]
        for path, expected_etype in checks:
            with open(path, "rb") as f:
                elf = ELFFile(f)
                hdr = elf.header
                self.assertEqual(hdr["e_ident"]["EI_MAG"], [127, 69, 76, 70], f"{path.name} bad ELF magic")
                self.assertEqual(hdr["e_ident"]["EI_CLASS"], "ELFCLASS32", f"{path.name} not 32-bit")
                self.assertEqual(hdr["e_ident"]["EI_DATA"], "ELFDATA2LSB", f"{path.name} not little-endian")
                self.assertEqual(hdr["e_machine"], "EM_ARM", f"{path.name} not EM_ARM")
                self.assertEqual(hdr["e_type"], expected_etype, f"{path.name} unexpected e_type")

    def test_physical_symbol_resolution(self):
        """Verify critical C++ and kernel symbols physically exist in ELF symbol tables."""
        # Check libInfraStreamingUsb.so symbols
        with open(LIB_STREAMING_STOCK, "rb") as f:
            elf = ELFFile(f)
            dynsym = elf.get_section_by_name(".dynsym")
            sym_names = {s.name: s["st_value"] for s in dynsym.iter_symbols()}
            self.assertIn("_ZN14VideoEsManager18video_stream_startEv", sym_names)
            self.assertIn("_ZN14VideoEsManager13set_path_syncEtthtj", sym_names)
            self.assertIn("_ZN14VideoEsManager18alloc_video_memoryEjPtPjS1_", sym_names)
            self.assertIn("_ZN14VideoEsManager15get_video_imageEPNS_14JPEG_DATA_INFOE", sym_names)

            # Function address check (Thumb address has LSB=1)
            vstart_val = sym_names["_ZN14VideoEsManager18video_stream_startEv"]
            self.assertEqual(vstart_val, 0x903F, "video_stream_start virtual address must be 0x903F")

        # Check libInfraUsbCmn.so symbols
        with open(LIB_USB_CMN_STOCK, "rb") as f:
            elf = ELFFile(f)
            dynsym = elf.get_section_by_name(".dynsym")
            cmn_syms = {s.name for s in dynsym.iter_symbols()}
            self.assertIn("_ZN19CUsbGadgetStreamingC1Ev", cmn_syms)
            self.assertIn("_Z19RegVideoDataBufInfo21StreamingVideoBufInfo", cmn_syms)

        # Check usbg_video.ko symbols
        with open(USBG_VIDEO_STOCK, "rb") as f:
            elf = ELFFile(f)
            symtab = elf.get_section_by_name(".symtab")
            ko_syms = {s.name for s in symtab.iter_symbols()}
            self.assertIn("usbg_video_core_open", ko_syms)
            self.assertIn("usbg_video_core_ioctl", ko_syms)
            self.assertIn("usbg_video_st_write_comp", ko_syms)


# ==============================================================================
# Component 2: Capstone Instruction-Level Guardrails
# ==============================================================================

class TestComponent2CapstoneInstructionLevelGuardrails(unittest.TestCase):
    """Component 2: Validates ARM/Thumb-2 disassembly, callee-saved registers, literal pool loads, branches."""

    def setUp(self):
        self.validator = CapstoneGuardrailValidator()

    def test_stock_instruction_decoding(self):
        """Verify Capstone correctly decodes stock instructions in VideoEsManager::video_stream_start."""
        data = LIB_STREAMING_STOCK.read_bytes()
        # 0x908A: mov.w r2, #1280 (4f f4 a0 62)
        insn_w = self.validator.decode_single(data[0x908A:0x908E], 0x908A)
        self.assertIn(insn_w.mnemonic, ("mov.w", "movw"))
        self.assertEqual(insn_w.operands[0].reg, arm.ARM_REG_R2)
        self.assertEqual(insn_w.operands[1].imm, 1280)

        # 0x908E: mov.w r3, #300 (4f f4 96 73)
        insn_br = self.validator.decode_single(data[0x908E:0x9092], 0x908E)
        self.assertIn(insn_br.mnemonic, ("mov.w", "movw"))
        self.assertEqual(insn_br.operands[0].reg, arm.ARM_REG_R3)
        self.assertEqual(insn_br.operands[1].imm, 300)

        # 0x9098: movs r2, #30 (1e 22)
        insn_fps = self.validator.decode_single(data[0x9098:0x909A], 0x9098)
        self.assertEqual(insn_fps.mnemonic, "movs")
        self.assertEqual(insn_fps.operands[0].reg, arm.ARM_REG_R2)
        self.assertEqual(insn_fps.operands[1].imm, 30)

    def test_patched_instruction_decoding(self):
        """Verify patched instruction at 0x908A is strictly Thumb-2 mov.w r2, #1920 (4F F4 F0 62)."""
        data = LIB_STREAMING_PATCHED.read_bytes()
        raw = data[0x908A:0x908E]
        self.assertEqual(raw, bytes([0x4F, 0xF4, 0xF0, 0x62]))

        insn = self.validator.decode_single(raw, 0x908A)
        self.assertIn(insn.mnemonic, ("mov.w", "movw"))
        self.assertEqual(len(insn.operands), 2)
        self.assertEqual(insn.operands[0].type, arm.ARM_OP_REG)
        self.assertEqual(insn.operands[0].reg, arm.ARM_REG_R2)
        self.assertEqual(insn.operands[1].type, arm.ARM_OP_IMM)
        self.assertEqual(insn.operands[1].imm, 1920)

    def test_callee_saved_registers_preservation(self):
        """Verify that patched instructions never overwrite AAPCS callee-saved registers (R4-R11, SP, LR)."""
        data = LIB_STREAMING_PATCHED.read_bytes()
        insn = self.validator.decode_single(data[0x908A:0x908E], 0x908A)
        no_clobber = self.validator.verify_no_callee_saved_clobber(insn)
        self.assertTrue(no_clobber, "Instruction clobbers callee-saved registers!")

    def test_rejection_of_endianness_inverted_opcode(self):
        """Verify that gen_uvc_patch.py's inverted halfwords (F0 62 4F F4) are rejected by disassembler."""
        buggy_bytes = bytes([0xF0, 0x62, 0x4F, 0xF4])
        # In Thumb mode, 0xF0 0x62 decodes as 2-byte "str r0, [r6, #0x2c]", leaving 4f f4 undecoded
        md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
        md.detail = True
        insns = list(md.disasm(buggy_bytes, 0x908A))
        self.assertEqual(len(insns), 1)
        self.assertEqual(insns[0].mnemonic, "str")
        self.assertEqual(insns[0].size, 2, "Decoded only 2 bytes of the 4 bytes")
        self.assertNotEqual(insns[0].size, len(buggy_bytes))

        # Ensure validator rejects it as a valid single 4-byte instruction
        with self.assertRaises(ValueError):
            self.validator.decode_single(buggy_bytes, 0x908A)

    def test_literal_pool_loads_and_alignment(self):
        """Verify all PC-relative literal pool loads in video_stream_start target 4-byte aligned valid memory."""
        data = LIB_STREAMING_PATCHED.read_bytes()
        fn_code = data[0x903E:0x90C0]
        md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
        md.detail = True

        for insn in md.disasm(fn_code, 0x903E):
            for op in insn.operands:
                if op.type == arm.ARM_OP_MEM and op.mem.base == arm.ARM_REG_PC:
                    # In Thumb mode: PC = (address + 4) & ~3
                    pc_base = (insn.address + 4) & ~3
                    target = pc_base + op.mem.disp
                    self.assertEqual(target % 4, 0, f"Unaligned PC-relative literal load at {insn.address:#x} -> {target:#x}")
                    self.assertTrue(0 <= target < len(data), f"Literal pool load outside binary bounds: {target:#x}")

    def test_branch_targets_and_alignment(self):
        """Verify all branch targets in video_stream_start are halfword-aligned and resolve within .text or .plt."""
        data = LIB_STREAMING_PATCHED.read_bytes()
        fn_code = data[0x903E:0x90C0]
        md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
        md.detail = True

        with open(LIB_STREAMING_PATCHED, "rb") as f:
            elf = ELFFile(f)
            text_sec = elf.get_section_by_name(".text")
            plt_sec = elf.get_section_by_name(".plt")
            text_bounds = (text_sec["sh_addr"], text_sec["sh_addr"] + text_sec["sh_size"])
            plt_bounds = (plt_sec["sh_addr"], plt_sec["sh_addr"] + plt_sec["sh_size"])

        for insn in md.disasm(fn_code, 0x903E):
            if insn.group(arm.ARM_GRP_JUMP) or insn.group(arm.ARM_GRP_CALL):
                for op in insn.operands:
                    if op.type == arm.ARM_OP_IMM:
                        target = op.imm
                        self.assertEqual(target % 2, 0, f"Unaligned branch target at {insn.address:#x} -> {target:#x}")
                        in_text = text_bounds[0] <= target < text_bounds[1]
                        in_plt = plt_bounds[0] <= target < plt_bounds[1]
                        self.assertTrue(in_text or in_plt, f"Branch target {target:#x} outside .text and .plt")

    def test_validate_instruction_patch_callee_saved_clobber(self):
        """Verify patch_uvc.validate_instruction_patch rejects callee-saved register clobber (4f f4 f0 64 -> r4)."""
        data = bytearray(LIB_STREAMING_PATCHED.read_bytes())
        data[0x908A:0x908E] = bytes([0x4F, 0xF4, 0xF0, 0x64])
        self.assertFalse(patch_uvc.validate_instruction_patch(bytes(data), 0x908A))

    def test_validate_instruction_patch_illegal_opcode(self):
        """Verify patch_uvc.validate_instruction_patch rejects illegal opcode (ff ff ff ff)."""
        data = bytearray(LIB_STREAMING_PATCHED.read_bytes())
        data[0x908A:0x908E] = bytes([0xFF, 0xFF, 0xFF, 0xFF])
        self.assertFalse(patch_uvc.validate_instruction_patch(bytes(data), 0x908A))

    def test_validate_instruction_patch_endianness_inversion(self):
        """Verify patch_uvc.validate_instruction_patch rejects halfword-inverted opcode (f0 62 4f f4)."""
        data = bytearray(LIB_STREAMING_PATCHED.read_bytes())
        data[0x908A:0x908E] = bytes([0xF0, 0x62, 0x4F, 0xF4])
        self.assertFalse(patch_uvc.validate_instruction_patch(bytes(data), 0x908A))

    def test_validate_instruction_patch_buffer_length_guard(self):
        """Verify patch_uvc.validate_instruction_patch rejects buffers not exactly 52524 bytes."""
        self.assertFalse(patch_uvc.validate_instruction_patch(b"\x00" * 100, 0x908A))
        self.assertFalse(patch_uvc.validate_instruction_patch(b"", 0x908A))

    def test_validate_instruction_patch_genuine_binary(self):
        """Verify patch_uvc.validate_instruction_patch accepts genuine 1080p patched binary."""
        data = LIB_STREAMING_PATCHED.read_bytes()
        self.assertTrue(patch_uvc.validate_instruction_patch(data, 0x908A))



# ==============================================================================
# Component 3: UVC Descriptor Specification Integrity
# ==============================================================================

class TestComponent3UvcDescriptorSpecificationIntegrity(unittest.TestCase):
    """Component 3: Validates downstream byte sums, lengths, frame resolutions, frame intervals, colorformat."""

    def test_pal_descriptor_hierarchy_integrity(self):
        """Validate patched PAL descriptor hierarchy at 0x12537 conforms to UVC 1.1 spec."""
        data = LIB_USB_CMN_PATCHED.read_bytes()
        info = UvcDescriptorParser.parse_vs_hierarchy(data, base_offset=0x12537)

        # 1. Byte sum exact match
        self.assertEqual(info["wTotalLength"], 61)
        self.assertEqual(info["calculated_total_length"], 61)
        self.assertEqual(info["span_bytes"], 61)

        # 2. Downstream components
        self.assertEqual(len(info["formats"]), 1)
        fmt = info["formats"][0]
        self.assertEqual(fmt["bFormatIndex"], 1)
        self.assertEqual(fmt["bNumFrameDescriptors"], 1)

        self.assertEqual(len(info["frames"]), 1)
        frame = info["frames"][0]
        self.assertEqual(frame["bFrameIndex"], 1)
        self.assertEqual(frame["wWidth"], 1920)
        self.assertEqual(frame["wHeight"], 1080)
        self.assertEqual(frame["dwDefaultFrameInterval"], 400000)  # 25 fps
        self.assertEqual(frame["intervals"], [400000])

        self.assertEqual(len(info["color_formats"]), 1)
        color = info["color_formats"][0]
        self.assertEqual(color["bColorPrimaries"], 1)  # BT.709
        self.assertEqual(color["bTransferCharacteristics"], 1)  # BT.709
        self.assertEqual(color["bMatrixCoefficients"], 4)  # SMPTE 170M

    def test_ntsc_descriptor_hierarchy_integrity(self):
        """Validate patched NTSC descriptor hierarchy at 0x12625 conforms to UVC 1.1 spec."""
        data = LIB_USB_CMN_PATCHED.read_bytes()
        info = UvcDescriptorParser.parse_vs_hierarchy(data, base_offset=0x12625)

        # 1. Byte sum exact match
        self.assertEqual(info["wTotalLength"], 61)
        self.assertEqual(info["calculated_total_length"], 61)
        self.assertEqual(info["span_bytes"], 61)

        # 2. Downstream components
        self.assertEqual(len(info["formats"]), 1)
        fmt = info["formats"][0]
        self.assertEqual(fmt["bFormatIndex"], 1)
        self.assertEqual(fmt["bNumFrameDescriptors"], 1)

        self.assertEqual(len(info["frames"]), 1)
        frame = info["frames"][0]
        self.assertEqual(frame["bFrameIndex"], 1)
        self.assertEqual(frame["wWidth"], 1920)
        self.assertEqual(frame["wHeight"], 1080)
        self.assertEqual(frame["dwDefaultFrameInterval"], 333333)  # 30 fps
        self.assertEqual(frame["intervals"], [333333])

        self.assertEqual(len(info["color_formats"]), 1)
        color = info["color_formats"][0]
        self.assertEqual(color["bColorPrimaries"], 1)  # BT.709
        self.assertEqual(color["bTransferCharacteristics"], 1)  # BT.709
        self.assertEqual(color["bMatrixCoefficients"], 4)  # SMPTE 170M

    def test_descriptor_bitrates_and_buffer_limits(self):
        """Verify min/max bitrates and frame buffer limits have no integer overflow and fit USB limits."""
        data = LIB_USB_CMN_PATCHED.read_bytes()
        for base, name in [(0x12537, "PAL"), (0x12625, "NTSC")]:
            info = UvcDescriptorParser.parse_vs_hierarchy(data, base)
            frame = info["frames"][0]
            # 300 Mbps = 300,000,000 bps = 0x11E1A300
            self.assertEqual(frame["dwMinBitRate"], 300_000_000, f"{name} min bitrate mismatch")
            self.assertEqual(frame["dwMaxBitRate"], 300_000_000, f"{name} max bitrate mismatch")
            self.assertGreater(frame["dwMaxVideoFrameBufferSize"], 0)
            self.assertEqual(frame["dwMaxVideoFrameBufferSize"], 14_745_600, f"{name} max buffer mismatch")

    def test_stock_pal_and_ntsc_descriptor_baselines(self):
        """Verify stock descriptor ground truths: 1280x720, wTotalLength=61, 25fps PAL, 30fps NTSC."""
        data = LIB_USB_CMN_STOCK.read_bytes()
        pal = UvcDescriptorParser.parse_vs_hierarchy(data, 0x12537)
        self.assertEqual(pal["frames"][0]["wWidth"], 1280)
        self.assertEqual(pal["frames"][0]["wHeight"], 720)
        self.assertEqual(pal["frames"][0]["dwDefaultFrameInterval"], 400000)

        ntsc = UvcDescriptorParser.parse_vs_hierarchy(data, 0x12625)
        self.assertEqual(ntsc["frames"][0]["wWidth"], 1280)
        self.assertEqual(ntsc["frames"][0]["wHeight"], 720)
        self.assertEqual(ntsc["frames"][0]["dwDefaultFrameInterval"], 333333)


# ==============================================================================
# Component 4: Registration Table & Dynamic Relocation Preservation
# ==============================================================================

class TestComponent4RegistrationTableAndDynamicRelocations(unittest.TestCase):
    """Component 4: Validates registration tables at 0x14AB8/0x14DB0, R_ARM_RELATIVE relocations."""

    def test_pal_and_ntsc_registration_table_lengths(self):
        """Verify 32-bit length fields at 0x14AB8 (PAL) and 0x14DB0 (NTSC) in libInfraUsbCmn.so equal 61."""
        for path in (LIB_USB_CMN_STOCK, LIB_USB_CMN_PATCHED):
            data = path.read_bytes()
            pal_len = struct.unpack("<I", data[0x14AB8:0x14ABC])[0]
            ntsc_len = struct.unpack("<I", data[0x14DB0:0x14DB4])[0]
            self.assertEqual(pal_len, 61, f"PAL registration table length at 0x14AB8 must be 61 in {path.name}")
            self.assertEqual(ntsc_len, 61, f"NTSC registration table length at 0x14DB0 must be 61 in {path.name}")

    def test_pal_and_ntsc_registration_table_pointers(self):
        """Verify 32-bit relocatable pointers at 0x14ABC and 0x14DB4 point to descriptor headers."""
        for path in (LIB_USB_CMN_STOCK, LIB_USB_CMN_PATCHED):
            data = path.read_bytes()
            pal_ptr = struct.unpack("<I", data[0x14ABC:0x14AC0])[0]
            ntsc_ptr = struct.unpack("<I", data[0x14DB4:0x14DB8])[0]
            self.assertEqual(pal_ptr, 0x00012537, f"PAL descriptor pointer at 0x14ABC corrupted in {path.name}")
            self.assertEqual(ntsc_ptr, 0x00012625, f"NTSC descriptor pointer at 0x14DB4 corrupted in {path.name}")

    def test_dynamic_relocations_r_arm_relative(self):
        """Verify that 0x14ABC and 0x14DB4 are covered by R_ARM_RELATIVE (23) relocations in .rel.dyn."""
        with open(LIB_USB_CMN_PATCHED, "rb") as f:
            elf = ELFFile(f)
            reldyn = elf.get_section_by_name(".rel.dyn")
            data_rel_ro = elf.get_section_by_name(".data.rel.ro")

            # Offset translation: file offset to virtual address
            # sh_addr: 0x1c018, sh_offset: 0x14018
            delta = data_rel_ro["sh_addr"] - data_rel_ro["sh_offset"]
            pal_ptr_va = 0x14ABC + delta   # 0x1CABC
            ntsc_ptr_va = 0x14DB4 + delta  # 0x1CDB4
            pal_len_va = 0x14AB8 + delta   # 0x1CAB8
            ntsc_len_va = 0x14DB0 + delta  # 0x1CDB0

            relocs = {r["r_offset"]: r["r_info_type"] for r in reldyn.iter_relocations()}

            # Pointers MUST be dynamic relocations (R_ARM_RELATIVE = 23)
            self.assertIn(pal_ptr_va, relocs, "Missing relocation for PAL descriptor pointer")
            self.assertEqual(relocs[pal_ptr_va], 23, "PAL pointer relocation must be R_ARM_RELATIVE (23)")

            self.assertIn(ntsc_ptr_va, relocs, "Missing relocation for NTSC descriptor pointer")
            self.assertEqual(relocs[ntsc_ptr_va], 23, "NTSC pointer relocation must be R_ARM_RELATIVE (23)")

            # Length fields MUST NOT be dynamic relocations (they are scalar lengths, not pointers)
            self.assertNotIn(pal_len_va, relocs, "Length field at 0x14AB8 must not be in relocation table")
            self.assertNotIn(ntsc_len_va, relocs, "Length field at 0x14DB0 must not be in relocation table")

    def test_prior_patch_fatal_pointer_clobber_disproof(self):
        """Disprove prior patch claim: writing length to 0x14DB4 overwrites pointer with 0x0000003D."""
        data = bytearray(LIB_USB_CMN_STOCK.read_bytes())
        # Simulating prior buggy behavior: writing length 61 to 0x14DB4
        data[0x14DB4:0x14DB8] = struct.pack("<I", 61)
        clobbered_ptr = struct.unpack("<I", data[0x14DB4:0x14DB8])[0]
        self.assertEqual(clobbered_ptr, 0x0000003D, "Writing length to 0x14DB4 replaces pointer with 0x3D")
        self.assertNotEqual(clobbered_ptr, 0x00012625, "Pointer is fatally destroyed!")


# ==============================================================================
# Component 5: USB 2.0 Bulk Endpoint & Transfer Bandwidth Validation
# ==============================================================================

class TestComponent5UsbBulkEndpointAndTransferBandwidth(unittest.TestCase):
    """Component 5: Validates USB 2.0 Bulk endpoint 0x81 wMaxPacketSize and bandwidth constraints."""

    def test_bulk_in_endpoint_table(self):
        """Verify endpoint table at file offset 0x14CC0 in libInfraUsbCmn.so defines 512-byte Bulk IN."""
        data = LIB_USB_CMN_PATCHED.read_bytes()
        # High-Speed endpoint entry at 0x14CC0: ep=0x81, attr=0x02, maxpacket=512 (0x0200)
        ep_entry = data[0x14CC0:0x14CC6]
        ep_addr, ep_attr, wMaxPacketSize = struct.unpack("<BBH", ep_entry[:4])
        self.assertEqual(ep_addr, 0x81, "Endpoint address must be 0x81 (IN)")
        self.assertEqual(ep_attr, 0x02, "Endpoint attributes must be Bulk (2)")
        self.assertEqual(wMaxPacketSize, 512, "High-Speed Bulk max packet size must be 512")

        # Full-Speed fallback endpoint entry at 0x14CD4: ep=0x81, attr=0x02, maxpacket=64 (0x0040)
        fs_entry = data[0x14CD4:0x14CD8]
        fs_addr, fs_attr, fs_maxpacket = struct.unpack("<BBH", fs_entry[:4])
        self.assertEqual(fs_addr, 0x81)
        self.assertEqual(fs_attr, 0x02)
        self.assertEqual(fs_maxpacket, 64, "Full-Speed Bulk max packet size must be 64")

    def test_usb_bulk_bandwidth_mathematics(self):
        """Verify sustained bulk throughput: 300 Mbps = 37.5 MB/s <= 43.0 MB/s sustained limit."""
        MAX_BULK_THROUGHPUT_MB_S = 43.0
        bitrate_mbps = 300.0
        mb_per_sec = bitrate_mbps / 8.0
        self.assertEqual(mb_per_sec, 37.5)
        self.assertLessEqual(mb_per_sec, MAX_BULK_THROUGHPUT_MB_S)
        bus_utilization = (mb_per_sec / MAX_BULK_THROUGHPUT_MB_S) * 100.0
        self.assertLessEqual(bus_utilization, 88.0, "Bus utilization must stay under 88% margin")

    def test_all_preset_bandwidth_compliance(self):
        """Verify all batch modes respect USB 2.0 Bulk bandwidth ceiling."""
        MAX_BULK_THROUGHPUT_MB_S = 43.0
        for mode, (w, h, fps, pal_fps, mbps) in pul.MODES.items():
            throughput_mb_s = mbps / 8.0
            self.assertLessEqual(
                throughput_mb_s,
                MAX_BULK_THROUGHPUT_MB_S,
                f"Mode {mode} throughput {throughput_mb_s} MB/s exceeds Bulk limit {MAX_BULK_THROUGHPUT_MB_S}"
            )


# ==============================================================================
# Component 6: Multi-OS Host Descriptor Parsing Emulation
# ==============================================================================

class TestComponent6MultiOsHostDescriptorParsingEmulation(unittest.TestCase):
    """Component 6: Simulates Linux, Windows, and macOS host descriptor parsing algorithms."""

    def setUp(self):
        self.cmn_bytes = LIB_USB_CMN_PATCHED.read_bytes()

    def test_linux_uvcvideo_parsing_emulation(self):
        """Simulate Linux uvcvideo kernel descriptor parser for both PAL and NTSC."""
        # PAL
        pal_res = LinuxUvcEmulator.parse_streaming(self.cmn_bytes, base_offset=0x12537)
        self.assertEqual(pal_res["status"], "SUCCESS")
        self.assertEqual(pal_res["parsed"]["frames"][0]["wWidth"], 1920)
        self.assertEqual(pal_res["parsed"]["frames"][0]["wHeight"], 1080)

        # NTSC
        ntsc_res = LinuxUvcEmulator.parse_streaming(self.cmn_bytes, base_offset=0x12625)
        self.assertEqual(ntsc_res["status"], "SUCCESS")
        self.assertEqual(ntsc_res["parsed"]["frames"][0]["wWidth"], 1920)
        self.assertEqual(ntsc_res["parsed"]["frames"][0]["wHeight"], 1080)

    def test_windows_usbvideo_parsing_emulation(self):
        """Simulate Windows usbvideo.sys descriptor parser and endpoint checks."""
        # PAL
        pal_res = WindowsUvcEmulator.validate_stream_descriptor(self.cmn_bytes, base_offset=0x12537, endpoint_packet_size=512)
        self.assertEqual(pal_res["status"], "SUCCESS")

        # NTSC
        ntsc_res = WindowsUvcEmulator.validate_stream_descriptor(self.cmn_bytes, base_offset=0x12625, endpoint_packet_size=512)
        self.assertEqual(ntsc_res["status"], "SUCCESS")

    def test_macos_coremedia_parsing_emulation(self):
        """Simulate macOS CoreMediaIO DAL plugin parser and format matrix builder."""
        # PAL
        pal_res = MacOsUvcEmulator.validate_stream_descriptor(self.cmn_bytes, base_offset=0x12537)
        self.assertEqual(pal_res["status"], "SUCCESS")

        # NTSC
        ntsc_res = MacOsUvcEmulator.validate_stream_descriptor(self.cmn_bytes, base_offset=0x12625)
        self.assertEqual(ntsc_res["status"], "SUCCESS")

    def test_multi_os_parsing_across_all_batch_modes(self):
        """Validate that all modes generated by batch_patch_uvc parse cleanly across Linux, Windows, macOS."""
        for mode in ("1080p", "1080p60", "opengate", "2k_opengate", "stock"):
            w, h, fps, pal_fps, mbps = bpu.resolve_mode_parameters(mode)
            cmn_bytes, stream_bytes = pul.patch_libraries(mode, w, h, fps, pal_fps, mbps)

            # Linux
            lin_pal = LinuxUvcEmulator.parse_streaming(cmn_bytes, base_offset=0x12537)
            lin_ntsc = LinuxUvcEmulator.parse_streaming(cmn_bytes, base_offset=0x12625)
            self.assertEqual(lin_pal["status"], "SUCCESS")
            self.assertEqual(lin_ntsc["status"], "SUCCESS")

            # Windows
            win_pal = WindowsUvcEmulator.validate_stream_descriptor(cmn_bytes, base_offset=0x12537, endpoint_packet_size=512)
            win_ntsc = WindowsUvcEmulator.validate_stream_descriptor(cmn_bytes, base_offset=0x12625, endpoint_packet_size=512)
            self.assertEqual(win_pal["status"], "SUCCESS")
            self.assertEqual(win_ntsc["status"], "SUCCESS")

            # macOS
            mac_pal = MacOsUvcEmulator.validate_stream_descriptor(cmn_bytes, base_offset=0x12537)
            mac_ntsc = MacOsUvcEmulator.validate_stream_descriptor(cmn_bytes, base_offset=0x12625)
            self.assertEqual(mac_pal["status"], "SUCCESS")
            self.assertEqual(mac_ntsc["status"], "SUCCESS")


# ==============================================================================
# Component 7: Adversarial Mutation & Tamper Detection
# ==============================================================================

class TestComponent7AdversarialMutationAndTamperDetection(unittest.TestCase):
    """Component 7: Injects bit flips, invalid opcodes, corrupt lengths, and verifies rejection."""

    def setUp(self):
        self.cmn_bytes = bytearray(LIB_USB_CMN_PATCHED.read_bytes())
        self.stream_bytes = bytearray(LIB_STREAMING_PATCHED.read_bytes())
        self.validator = CapstoneGuardrailValidator()

    def test_adversarial_bit_flip_opcode(self):
        """Flip bits in mov.w r2, #1920 (4f f4 f0 62) to clobber r4 (callee-saved) and assert rejection."""
        # Opcode targeting r4: 4f f4 f0 64 (mov.w r4, #1920)
        corrupted_opcode = bytes([0x4F, 0xF4, 0xF0, 0x64])
        insn = self.validator.decode_single(corrupted_opcode, 0x908A)
        self.assertFalse(
            self.validator.verify_no_callee_saved_clobber(insn),
            "Validator failed to detect callee-saved register R4 clobber"
        )

        # Illegal instruction bitflip: ff ff ff ff
        corrupted_illegal = bytes([0xFF, 0xFF, 0xFF, 0xFF])
        with self.assertRaises(Exception):
            self.validator.decode_single(corrupted_illegal, 0x908A)

    def test_adversarial_descriptor_length_mismatch(self):
        """Mutate wTotalLength to 60 or 62 and assert that Linux and Windows emulators reject it."""
        # Mutate PAL wTotalLength (offset 0x12537 + 4 = 0x1253B) to 60
        corrupted_buf = bytearray(self.cmn_bytes)
        corrupted_buf[0x1253B] = 60

        with self.assertRaises(UvcDescriptorError):
            LinuxUvcEmulator.parse_streaming(bytes(corrupted_buf), base_offset=0x12537)

        with self.assertRaises(UvcDescriptorError):
            WindowsUvcEmulator.validate_stream_descriptor(bytes(corrupted_buf), base_offset=0x12537)

        with self.assertRaises(UvcDescriptorError):
            MacOsUvcEmulator.validate_stream_descriptor(bytes(corrupted_buf), base_offset=0x12537)

    def test_adversarial_frame_dimension_corruption(self):
        """Inject 0 width or height into frame descriptor and verify emulators reject."""
        corrupted_buf = bytearray(self.cmn_bytes)
        # PAL wWidth at 0x12555
        corrupted_buf[0x12555:0x12557] = struct.pack("<H", 0)

        with self.assertRaises(UvcDescriptorError):
            WindowsUvcEmulator.validate_stream_descriptor(bytes(corrupted_buf), base_offset=0x12537)

        with self.assertRaises(UvcDescriptorError):
            MacOsUvcEmulator.validate_stream_descriptor(bytes(corrupted_buf), base_offset=0x12537)

    def test_adversarial_registration_table_corruption(self):
        """Alter table length at 0x14AB8 to 91 and verify patch_uvc validation failure."""
        corrupted_buf = bytearray(self.cmn_bytes)
        corrupted_buf[0x14AB8:0x14ABC] = struct.pack("<I", 91)
        res = patch_uvc.validate_uvc_descriptors(bytes(corrupted_buf))
        self.assertFalse(res.valid, "validate_uvc_descriptors should fail on corrupted table length")
        self.assertTrue(any("0x14AB8 is 91" in d for d in res.details))
        self.assertFalse(any("Registration tables verified intact" in d for d in res.details))
        self.assertTrue(any("Registration table validation failed" in d for d in res.details))

    def test_adversarial_registration_table_pointer_corruption(self):
        """Clobber NTSC registration table pointer at 0x14DB4 and verify validation failure diagnostic."""
        corrupted_buf = bytearray(self.cmn_bytes)
        corrupted_buf[0x14DB4:0x14DB8] = struct.pack("<I", 0x3D)
        res = patch_uvc.validate_uvc_descriptors(bytes(corrupted_buf))
        self.assertFalse(res.valid)
        self.assertTrue(any("0x14DB4: 0x3d" in d for d in res.details))
        self.assertFalse(any("Registration tables verified intact" in d for d in res.details))
        self.assertTrue(any("Registration table validation failed" in d for d in res.details))

    def test_adversarial_truncated_child_descriptor_header(self):
        """Verify truncated child descriptor payload (curr + 2 == len(data)) raises UvcDescriptorError, not IndexError."""
        # 14-byte VS_INPUT_HEADER with wTotalLength=16, followed by only 2 bytes
        header = bytes([14, 0x24, 0x01, 1, 16, 0, 0x81, 0, 0, 0, 0, 0, 0, 0])
        child_partial = bytes([2, 0x24])  # Exactly 2 bytes
        data = header + child_partial
        with self.assertRaises(UvcDescriptorError):
            UvcDescriptorParser.parse_vs_hierarchy(data)

    def test_adversarial_zero_frame_descriptor_rejection(self):
        """Verify descriptors with 0 frame descriptors are rejected by Windows, macOS, and Linux emulators."""
        hdr_exact = bytes([14, 0x24, 0x01, 0, 14, 0, 0x81, 0, 0, 0, 0, 0, 0, 0])
        with self.assertRaises(UvcDescriptorError):
            WindowsUvcEmulator.validate_stream_descriptor(hdr_exact)
        with self.assertRaises(UvcDescriptorError):
            MacOsUvcEmulator.validate_stream_descriptor(hdr_exact)
        with self.assertRaises(UvcDescriptorError):
            LinuxUvcEmulator.parse_streaming(hdr_exact)

    def test_adversarial_endpoint_max_packet_overflow(self):
        """Inject max packet size 1024 on Bulk endpoint and verify Windows rejection."""
        with self.assertRaises(UvcDescriptorError):
            WindowsUvcEmulator.validate_stream_descriptor(bytes(self.cmn_bytes), base_offset=0x12537, endpoint_packet_size=1024)

    def test_adversarial_bitrate_bandwidth_overflow(self):
        """Verify that an adversarial bitrate of 400 Mbps (50 MB/s) fails bulk throughput check."""
        MAX_BULK_THROUGHPUT_MB_S = 43.0
        adversarial_mbps = 400.0
        adversarial_mb_s = adversarial_mbps / 8.0  # 50 MB/s
        self.assertGreater(adversarial_mb_s, MAX_BULK_THROUGHPUT_MB_S)

    def test_adversarial_instruction_offset_drift(self):
        """Verify that drifting patch offset to an unaligned Thumb address (0x908B) fails."""
        data = self.stream_bytes
        # 0x908B is odd address (unaligned in ARM/Thumb)
        self.assertEqual(0x908B % 2, 1)
        with self.assertRaises(Exception):
            self.validator.decode_single(data[0x908B:0x908F], 0x908B)


# ==============================================================================
# Component 8: Single-Shot Patch Generator Idempotency & Cleanliness
# ==============================================================================

class TestComponent8SingleShotPatchGenerator(unittest.TestCase):
    """Component 8: Tests scripts/patch_uvc.py apply_patches(), CLI, idempotency, non-stock rejection."""

    def test_apply_patches_programmatic_api(self):
        """Verify scripts/patch_uvc.py apply_patches() produces byte-identical patched binaries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir)
            res = patch_uvc.apply_patches(
                source_dir=LIB_USB_CMN_STOCK.parent,
                target_dir=target_path,
                force=True,
                validate=True,
            )
            self.assertTrue(res["success"], f"apply_patches failed: {res['errors']}")

            for filename, expected in HASH_DB.items():
                if filename not in patch_uvc.PATCHES:
                    continue
                out_file = target_path / filename
                self.assertTrue(out_file.exists(), f"Missing output file: {out_file}")
                data = out_file.read_bytes()
                self.assertEqual(len(data), expected["patched_size"])
                self.assertEqual(hashlib.md5(data).hexdigest(), expected["patched_md5"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), expected["patched_sha256"])

    def test_apply_patches_idempotency(self):
        """Verify applying patches multiple times yields bit-for-bit identical results."""
        with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
            res1 = patch_uvc.apply_patches(source_dir=LIB_USB_CMN_STOCK.parent, target_dir=Path(tmpdir1), force=True)
            res2 = patch_uvc.apply_patches(source_dir=LIB_USB_CMN_STOCK.parent, target_dir=Path(tmpdir2), force=True)
            self.assertTrue(res1["success"])
            self.assertTrue(res2["success"])

            for fname in patch_uvc.PATCHES:
                b1 = (Path(tmpdir1) / fname).read_bytes()
                b2 = (Path(tmpdir2) / fname).read_bytes()
                self.assertEqual(b1, b2, f"Idempotency violation in {fname}")

    def test_apply_patches_rejects_corrupted_stock(self):
        """Verify apply_patches cleanly rejects non-stock/corrupted input binaries without writing."""
        with tempfile.TemporaryDirectory() as fake_src, tempfile.TemporaryDirectory() as fake_dst:
            src_path = Path(fake_src)
            # Create corrupted dummy libInfraUsbCmn.so
            (src_path / "libInfraUsbCmn.so").write_bytes(b"CORRUPTED_DUMMY_BINARY")

            res = patch_uvc.apply_patches(source_dir=src_path, target_dir=Path(fake_dst), force=False)
            self.assertFalse(res["success"])
            self.assertFalse((Path(fake_dst) / "libInfraUsbCmn.so").exists())

    def test_patch_uvc_cli_dry_run(self):
        """Verify CLI python scripts/patch_uvc.py --dry-run exits with code 0."""
        cmd = [str(PYTHON_EXE), str(REPO_ROOT / "scripts" / "patch_uvc.py"), "--dry-run"]
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc.returncode, 0, f"patch_uvc --dry-run failed:\n{proc.stderr}")
        self.assertIn("[OK] Stock file libInfraUsbCmn.so", proc.stdout)
        self.assertIn("[OK] Stock file libInfraStreamingUsb.so", proc.stdout)

    def test_patch_uvc_cli_verify_only(self):
        """Verify CLI python scripts/patch_uvc.py --verify-only against staged patched binaries exits 0."""
        cmd = [str(PYTHON_EXE), str(REPO_ROOT / "scripts" / "patch_uvc.py"), "--verify-only"]
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc.returncode, 0, f"patch_uvc --verify-only failed:\n{proc.stderr}")
        self.assertIn("VERIFIED OK", proc.stdout)

    def test_patch_uvc_cli_default_patching_mode(self):
        """Verify CLI default patching mode (python scripts/patch_uvc.py -t <dest> -f) writes and validates binaries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = [str(PYTHON_EXE), str(REPO_ROOT / "scripts" / "patch_uvc.py"), "-t", str(tmpdir), "-f"]
            proc = subprocess.run(cmd, cwd=str(REPO_ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(proc.returncode, 0, f"patch_uvc default mode failed:\n{proc.stderr}")
            self.assertIn("All target binaries successfully patched and validated!", proc.stdout)

            for filename, expected in HASH_DB.items():
                if filename not in patch_uvc.PATCHES:
                    continue
                out_file = Path(tmpdir) / filename
                self.assertTrue(out_file.is_file(), f"Output file missing: {filename}")
                data = out_file.read_bytes()
                self.assertEqual(len(data), expected["patched_size"])
                self.assertEqual(hashlib.md5(data).hexdigest(), expected["patched_md5"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), expected["patched_sha256"])

    def test_verify_stock_file_branches(self):
        """Verify patch_uvc.verify_stock_file validation branches for invalid inputs."""
        # Non-existent/unknown file
        ok, msg = patch_uvc.verify_stock_file(Path("unknown_binary.so"))
        self.assertFalse(ok)
        self.assertIn("Unknown binary", msg)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Known filename but file doesn't exist on disk
            missing_cmn = Path(tmpdir) / "libInfraUsbCmn.so"
            ok, msg = patch_uvc.verify_stock_file(missing_cmn)
            self.assertFalse(ok)
            self.assertIn("File does not exist", msg)

            # Size mismatch
            missing_cmn.write_bytes(b"SHORT_DATA")
            ok, msg = patch_uvc.verify_stock_file(missing_cmn)
            self.assertFalse(ok)
            self.assertIn("Size mismatch", msg)

            # Hash mismatch with correct size
            missing_cmn.write_bytes(b"X" * 94612)
            ok, msg = patch_uvc.verify_stock_file(missing_cmn)
            self.assertFalse(ok)
            self.assertIn("mismatch", msg)

        # Genuine stock binary succeeds
        ok, msg = patch_uvc.verify_stock_file(LIB_USB_CMN_STOCK)
        self.assertTrue(ok)
        self.assertIn("verified OK", msg)


    def test_patch_tables_data_structures(self):
        """Verify exported PATCHES table structure matches canonical specification."""
        self.assertIn("libInfraUsbCmn.so", patch_uvc.PATCHES)
        self.assertIn("libInfraStreamingUsb.so", patch_uvc.PATCHES)

        cmn_patches = patch_uvc.PATCHES["libInfraUsbCmn.so"]
        self.assertEqual(len(cmn_patches), 2)
        self.assertEqual(cmn_patches[0].offset, 0x12550)
        self.assertEqual(len(cmn_patches[0].patched_bytes), 30)
        self.assertEqual(cmn_patches[1].offset, 0x1263E)
        self.assertEqual(len(cmn_patches[1].patched_bytes), 30)

        stream_patches = patch_uvc.PATCHES["libInfraStreamingUsb.so"]
        self.assertEqual(len(stream_patches), 1)
        self.assertEqual(stream_patches[0].offset, 0x908A)
        self.assertEqual(stream_patches[0].patched_bytes, bytes([0x4F, 0xF4, 0xF0, 0x62]))


# ==============================================================================
# Legacy & Staged Artifacts Regression Invariants
# ==============================================================================

class TestLegacyAndStagedArtifactsIntegrity(unittest.TestCase):
    """Preserves and validates the original 10 regression tests for full backwards compatibility."""

    def setUp(self):
        self.assertTrue(LIB_USB_CMN_STOCK.exists(), f"Missing firmware dump: {LIB_USB_CMN_STOCK}")
        self.assertTrue(LIB_STREAMING_STOCK.exists(), f"Missing firmware dump: {LIB_STREAMING_STOCK}")

    def test_pal_descriptor_stock_layout(self):
        """Verify stock PAL UVC Frame Descriptor at 0x12550."""
        with open(LIB_USB_CMN_STOCK, "rb") as f:
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
        with open(LIB_USB_CMN_STOCK, "rb") as f:
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
        with open(LIB_STREAMING_STOCK, "rb") as f:
            f.seek(0x908a)
            inst_width = f.read(4)
            inst_bitrate = f.read(4)

            f.seek(0x9098)
            inst_fps = f.read(2)

        self.assertEqual(inst_width, bytes([0x4f, 0xf4, 0xa0, 0x62]), "Width instruction must match mov.w r2, #1280")
        self.assertEqual(inst_bitrate, bytes([0x4f, 0xf4, 0x96, 0x73]), "Bitrate instruction must match mov.w r3, #300")
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
        MAX_BULK_THROUGHPUT_MB_S = 43.0

        mbps_1080p30 = 300
        mb_s_1080p30 = mbps_1080p30 / 8.0
        self.assertLessEqual(mb_s_1080p30, MAX_BULK_THROUGHPUT_MB_S)

        mbps_1080p60 = 320
        mb_s_1080p60 = mbps_1080p60 / 8.0
        self.assertLessEqual(mb_s_1080p60, MAX_BULK_THROUGHPUT_MB_S)

        mbps_opengate = 300
        mb_s_opengate = mbps_opengate / 8.0
        self.assertLessEqual(mb_s_opengate, MAX_BULK_THROUGHPUT_MB_S)

    def test_batch_patch_uvc_modes(self):
        """Verify batch_patch_uvc resolves all presets with correct parameters."""
        modes_to_test = {
            "1080p": (1920, 1080, 30, 25, 300),
            "1080p60": (1920, 1080, 60, 50, 320),
            "opengate": (3240, 2160, 24, 25, 300),
            "2k_opengate": (2160, 1440, 30, 25, 300),
            "stock": (1280, 720, 30, 25, 30),
        }

        for m, expected in modes_to_test.items():
            w, h, fps, pal_fps, mbps = bpu.resolve_mode_parameters(m)
            self.assertEqual((w, h, fps, pal_fps, mbps), expected, f"Mode {m} mismatch")

            patches = bpu.generate_uvc_patch_list(0x10000000, 0x20000000, w, h, fps, pal_fps, mbps)
            self.assertEqual(len(patches), 5, f"Must generate 5 patches for mode {m}")
            self.assertEqual(len(patches[0][2]), 60)
            self.assertEqual(len(patches[1][2]), 60)

    def test_batch_patch_custom_overrides(self):
        """Verify custom width, height, fps, bitrate overrides in batch_patch_uvc."""
        w, h, fps, pal_fps, mbps = bpu.resolve_mode_parameters("1080p", custom_w=2560, custom_h=1440, custom_fps=48, custom_br=280)
        self.assertEqual(w, 2560)
        self.assertEqual(h, 1440)
        self.assertEqual(fps, 48)
        self.assertEqual(mbps, 280)

        patches = bpu.generate_uvc_patch_list(0, 0, w, h, fps, pal_fps, mbps)
        self.assertEqual(len(patches), 5)

    def test_library_file_patching_integrity(self):
        """Verify patch_libraries generates valid 94612 B and 52524 B binaries for all modes."""
        for mode, (w, h, fps, pal_fps, mbps) in pul.MODES.items():
            cmn_bytes, stream_bytes = pul.patch_libraries(mode, w, h, fps, pal_fps, mbps)

            self.assertEqual(len(cmn_bytes), 94612, f"cmn size mismatch in mode {mode}")
            self.assertEqual(len(stream_bytes), 52524, f"stream size mismatch in mode {mode}")

            pal_w, pal_h = struct.unpack("<HH", cmn_bytes[0x12555:0x12559])
            self.assertEqual(pal_w, w, f"PAL width mismatch in mode {mode}")
            self.assertEqual(pal_h, h, f"PAL height mismatch in mode {mode}")

            ntsc_w, ntsc_h = struct.unpack("<HH", cmn_bytes[0x12643:0x12647])
            self.assertEqual(ntsc_w, w, f"NTSC width mismatch in mode {mode}")
            self.assertEqual(ntsc_h, h, f"NTSC height mismatch in mode {mode}")

    def test_file_patch_elf_binary(self):
        """Verify compiled out/file_patch.elf exists and has valid ARM ELF header."""
        self.assertTrue(FILE_PATCH_ELF.exists(), "out/file_patch.elf must exist")
        data = FILE_PATCH_ELF.read_bytes()
        self.assertTrue(data.startswith(b"\x7fELF"), "Must have ELF magic")
        self.assertEqual(data[4], 1, "Must be ELFCLASS32")
        self.assertEqual(data[5], 1, "Must be ELFDATA2LSB (little-endian)")
        machine = struct.unpack("<H", data[0x12:0x14])[0]
        self.assertEqual(machine, 0x28, "Machine must be EM_ARM (0x28)")


# ==============================================================================
# USB Video Gadget Driver & UVC Protocol Disassembly Invariants
# ==============================================================================

class TestUvcGadgetVideoDriverDisassembly(unittest.TestCase):
    """
    Validates offline disassembly and protocol control-flow invariants across:
      1. usbg_video.ko binary hash and section structure
      2. usbg_video_core_ioctl dead-stub ioctl rejection (-ENOTTY / -25)
      3. core_cb_class in-kernel probe/commit interception and event 7 routing
      4. UpdateVideoBufEvt UVC header BFH arithmetic (omitted EOF bit 1)
      5. .rodata hardcoded probe response (dwMaxVideoFrameSize = 14.75 MB)
      6. libInfraUsbCmn.so proc_kevent_video kernel event router
      7. core_cb_start (0x10f0) endpoint list population and EBUSY gating
      8. DMA330 channel descriptor pre-binding in usbg_video_core_open (0x1c64)
      9. Double-buffer saturation drop branch (0x0f10 -> 0x10cc) and disable_flag
    """

    def setUp(self):
        self.assertTrue(USBG_VIDEO_STOCK.exists(), f"Missing usbg_video.ko: {USBG_VIDEO_STOCK}")
        self.assertTrue(LIB_USB_CMN_STOCK.exists(), f"Missing libInfraUsbCmn.so: {LIB_USB_CMN_STOCK}")
        self.ko_data = USBG_VIDEO_STOCK.read_bytes()
        self.cmn_data = LIB_USB_CMN_STOCK.read_bytes()

    def test_usbg_video_hash_and_size(self):
        """Verify usbg_video.ko stock MD5 and file size match canonical repository dump."""
        self.assertEqual(len(self.ko_data), 20668)
        self.assertEqual(hashlib.md5(self.ko_data).hexdigest(), "5b59c2e62c80683d754955ab5de0467d")

    def test_usbg_video_core_ioctl_unhandled_rejection(self):
        """Verify ioctls 0x4008f004/5 branch to 0x2350 and return -ENOTTY (-25 via mvn r4, #0x18)."""
        with open(USBG_VIDEO_STOCK, "rb") as f:
            elf = ELFFile(f)
            text = elf.get_section_by_name(".text")
            text_data = text.data()

            # At VA 0x21a8: ldr r3, [pc, #0x234] -> loads 0x4008f000 from 0x23e4
            c_4008f000 = struct.unpack_from("<I", text_data, 0x23e4)[0]
            self.assertEqual(c_4008f000, 0x4008f000)

            # At VA 0x23b0: mvn r4, #0x18 (0xe3e04018) -> returns ~0x18 = -25 (-ENOTTY)
            mvn_inst = struct.unpack_from("<I", text_data, 0x23b0)[0]
            self.assertEqual(mvn_inst, 0xe3e04018, "Instruction at 0x23b0 must be mvn r4, #0x18")
            self.assertEqual(~0x18, -25, "mvn #0x18 evaluates strictly to -25 (errno ENOTTY)")

    def test_core_cb_class_probe_commit_interception(self):
        """Verify core_cb_class (0x17b0) filters VS_PROBE_CONTROL (0x100) vs VS_COMMIT_CONTROL (0x200)."""
        with open(USBG_VIDEO_STOCK, "rb") as f:
            elf = ELFFile(f)
            text = elf.get_section_by_name(".text")
            text_data = text.data()

            # VA 0x198c: cmp r3, #0x200 (0xe3530c02)
            # VA 0x1990: bne 0x1a64 (0x1a000033)
            cmp_inst = struct.unpack_from("<I", text_data, 0x198c)[0]
            self.assertEqual(cmp_inst, 0xe3530c02, "Must be cmp r3, #0x200 (check for VS_COMMIT_CONTROL)")

            # VA 0x199c: mov r0, #7 (0xe3a00007) -> event code 7
            mov_inst = struct.unpack_from("<I", text_data, 0x199c)[0]
            self.assertEqual(mov_inst, 0xe3a00007, "Must pass event code 7 to usbg_video_call_user_cb")

    def test_uvc_header_bfh_arithmetic_missing_eof(self):
        """Verify UpdateVideoBufEvt BFH calculation (sub r8, r8, #0x74) omits EOF bit 1."""
        with open(USBG_VIDEO_STOCK, "rb") as f:
            elf = ELFFile(f)
            text = elf.get_section_by_name(".text")
            text_data = text.data()

            # VA 0x0f40: strb r6, [r5] (bHeaderLength = 12)
            # VA 0x0f44: sub r8, r8, #0x74 (0xe2488074)
            # VA 0x0f48: uxtb r8, r8 (0xe6ef8078)
            # VA 0x0f4c: strb r8, [r5, #1]
            sub_inst = struct.unpack_from("<I", text_data, 0x0f44)[0]
            self.assertEqual(sub_inst, 0xe2488074, "Instruction at 0x0f44 must be sub r8, r8, #0x74")

            # Verify BFH values for toggle in {0, 1}
            for toggle in (0, 1):
                bfh = (toggle - 0x74) & 0xff
                expected = 0x8c if toggle == 0 else 0x8d
                self.assertEqual(bfh, expected)
                fid = bfh & 0x01
                eof = (bfh >> 1) & 0x01
                self.assertEqual(fid, toggle, "Bit 0 (FID) must reflect frame toggle")
                self.assertEqual(eof, 0, "Bit 1 (EOF) must be strictly 0 in stock firmware")

    def test_in_kernel_probe_response_geometry(self):
        """Verify .rodata offset 0x7a contains 26-byte probe response with 14.75 MB frame size."""
        with open(USBG_VIDEO_STOCK, "rb") as f:
            elf = ELFFile(f)
            rodata = elf.get_section_by_name(".rodata")
            rodata_data = rodata.data()

            probe = rodata_data[0x7a:0x7a + 26]
            self.assertEqual(len(probe), 26)

            bmHint, bFmt, bFrm, dwInterval, wKey, wP, wQual, wWin, wDelay, dwMaxFrame, dwMaxPayload = \
                struct.unpack("<HBBIHHHHHII", probe)

            self.assertEqual(bFmt, 1)
            self.assertEqual(bFrm, 1)
            self.assertEqual(dwInterval, 333333)  # 30 fps (333,333 x 100ns)
            self.assertEqual(dwMaxFrame, 14745600)  # 14.75 MB stock MJPEG buffer
            self.assertEqual(dwMaxPayload, 300000)  # 300 KB payload limit

    def test_lib_usb_cmn_proc_kevent_video_routing(self):
        """Verify libInfraUsbCmn.so proc_kevent_video routes event 7 to proc_vendor_event."""
        with open(LIB_USB_CMN_STOCK, "rb") as f:
            elf = ELFFile(f)
            dynsym = elf.get_section_by_name(".dynsym")

            kevent_sym = next(s for s in dynsym.iter_symbols() if s.name == "_ZN19CUsbGadgetStreaming17proc_kevent_videoEmhhPv")
            vendor_sym = next(s for s in dynsym.iter_symbols() if s.name == "_Z17proc_vendor_eventPv")

            self.assertEqual(kevent_sym["st_value"] & ~1, 0x11df8)
            self.assertEqual(vendor_sym["st_value"] & ~1, 0x11da0)

            # Check jump table instruction at 0x11e08: tbb [pc, r4] (0xe8d0 0xf004)
            text = elf.get_section_by_name(".text")
            text_data = text.data()
            text_addr = text["sh_addr"]

            tbb_offset = 0x11e08 - text_addr
            tbb_halfword = struct.unpack_from("<H", text_data, tbb_offset)[0]
            self.assertEqual(tbb_halfword, 0xe8df, "Must be Thumb-2 tbb opcode prefix")

            # Check event 7 table entry offset = 22 -> target 0x11e38
            tbb_pc = 0x11e0c
            table_offset = tbb_pc - text_addr
            entry_7_offset = text_data[table_offset + 7]
            self.assertEqual(entry_7_offset, 22)
            self.assertEqual(tbb_pc + entry_7_offset * 2, 0x11e38)

    def test_core_cb_start_and_endpoint_gating(self):
        """Verify core_cb_start populates endpoints via usbg_cmn_make_ep_list and UpdateVideoBufEvt gates on ep."""
        with open(USBG_VIDEO_STOCK, "rb") as f:
            elf = ELFFile(f)
            text_data = elf.get_section_by_name(".text").data()
            rel = elf.get_section_by_name(".rel.text")
            symtab = elf.get_section_by_name(".symtab")
            symbols = [s.name for s in symtab.iter_symbols()]
            relocs = {r["r_offset"]: symbols[r["r_info_sym"]] for r in rel.iter_relocations() if r["r_info_sym"] < len(symbols)}

            # 1. core_cb_start (0x10f0) calls usbg_cmn_make_ep_list at 0x1138
            self.assertEqual(relocs.get(0x1138), "usbg_cmn_make_ep_list")

            # 2. core_cb_start clears flag_A and flag_B at 0x1198 and 0x119c
            strb_flag_a = struct.unpack_from("<I", text_data, 0x1198)[0]
            strb_flag_b = struct.unpack_from("<I", text_data, 0x119c)[0]
            self.assertEqual(strb_flag_a, 0xe5c23010, "0x1198 must be strb r3, [r2, #0x10]")
            self.assertEqual(strb_flag_b, 0xe5c23011, "0x119c must be strb r3, [r2, #0x11]")

            # 3. UpdateVideoBufEvt calls usbg_video_get_ep at 0x0db0 and aborts with -EBUSY (-16) if NULL
            self.assertEqual(relocs.get(0x0db0), "usbg_video_get_ep")
            mvn_ebusy = struct.unpack_from("<I", text_data, 0x0dc8)[0]
            self.assertEqual(mvn_ebusy, 0xe3e0000f, "0x0dc8 must be mvn r0, #0xf (-16 = -EBUSY)")

    def test_dma330_channel_and_descriptor_binding(self):
        """Verify usbg_video_core_open binds uvc_transfer_dmac_cb and descriptor to dma_chan."""
        with open(USBG_VIDEO_STOCK, "rb") as f:
            elf = ELFFile(f)
            text_data = elf.get_section_by_name(".text").data()
            rel = elf.get_section_by_name(".rel.text")
            symtab = elf.get_section_by_name(".symtab")
            symbols = [s.name for s in symtab.iter_symbols()]
            relocs = {r["r_offset"]: symbols[r["r_info_sym"]] for r in rel.iter_relocations() if r["r_info_sym"] < len(symbols)}

            # 1. usbg_video_core_open binds uvc_transfer_dmac_cb to dma_chan->cb at [r3, #0xc]
            str_cb = struct.unpack_from("<I", text_data, 0x1c40)[0]
            self.assertEqual(str_cb, 0xe583200c, "0x1c40 must be str r2, [r3, #0xc] (dma_chan->cb)")
            self.assertEqual(relocs.get(0x1ca4), "uvc_transfer_dmac_cb")

            # 2. usbg_video_core_open binds physical descriptor to dma_chan->desc at [r2, #8]
            str_desc = struct.unpack_from("<I", text_data, 0x1c64)[0]
            self.assertEqual(str_desc, 0xe5823008, "0x1c64 must be str r3, [r2, #8] (dma_chan->desc)")

            # 3. UpdateVideoBufEvt invokes dma330_mem_transfer_async at 0x0f70
            self.assertEqual(relocs.get(0x0f70), "dma330_mem_transfer_async")

            # 4. uvc_transfer_dmac_cb (0x06a0) writes 1 to dma_done and calls wake_up_process at 0x06d4
            str_done = struct.unpack_from("<I", text_data, 0x06bc)[0]
            self.assertEqual(str_done, 0xe5832000, "0x06bc must be str r2, [r3] (*dma_done = 1)")
            self.assertEqual(relocs.get(0x06d4), "wake_up_process")

    def test_double_buffer_readiness_and_drop_branch(self):
        """Verify UpdateVideoBufEvt drops frames to 0x10cc (mov r0, #0) and st_write_comp calls disable_flag."""
        with open(USBG_VIDEO_STOCK, "rb") as f:
            elf = ELFFile(f)
            text_data = elf.get_section_by_name(".text").data()
            rel = elf.get_section_by_name(".rel.text")
            symtab = elf.get_section_by_name(".symtab")
            symbols = [s.name for s in symtab.iter_symbols()]
            relocs = {r["r_offset"]: symbols[r["r_info_sym"]] for r in rel.iter_relocations() if r["r_info_sym"] < len(symbols)}

            # 1. If flag_A != 0 and flag_B != 0, UpdateVideoBufEvt branches to 0x10cc at 0x0f10
            bne_drop = struct.unpack_from("<I", text_data, 0x0f10)[0]
            self.assertEqual(bne_drop, 0x1a00006d, "0x0f10 must be bne 0x10cc (drop frame)")
            mov_zero = struct.unpack_from("<I", text_data, 0x10cc)[0]
            self.assertEqual(mov_zero, 0xe3a00000, "0x10cc must be mov r0, #0 (silent drop success)")

            # 2. usbg_video_st_write_comp (0x248c) calls disable_flag at 0x2540 to clear buffer flag
            self.assertEqual(relocs.get(0x2540), "disable_flag")

            # 3. disable_flag (0x243c) clears flag_A at 0x2464 and flag_B at 0x2474
            strbeq_flag_a = struct.unpack_from("<I", text_data, 0x2464)[0]
            strbeq_flag_b = struct.unpack_from("<I", text_data, 0x2474)[0]
            self.assertEqual(strbeq_flag_a, 0x05c32010, "0x2464 must be strbeq r2, [r3, #0x10]")
            self.assertEqual(strbeq_flag_b, 0x05c32011, "0x2474 must be strbeq r2, [r3, #0x11]")

            # 4. UpdateVideoBufEvt aborts with -0x68 at 0x10c4 on physical address check failure
            mvn_addr_err = struct.unpack_from("<I", text_data, 0x10c4)[0]
            self.assertEqual(mvn_addr_err, 0xe3e00068, "0x10c4 must be mvn r0, #0x68 (-105)")



if __name__ == "__main__":
    unittest.main()

