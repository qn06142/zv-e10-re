#!/usr/bin/env python3
"""
Single-Shot Surgical Patch Generator for Sony ZV-E10 UVC 1080p Webcam Subsystem.

Applies verified, surgical binary modifications to elevate factory 720p UVC video
streaming to Full HD 1080p (1920x1080 @ 30fps NTSC / 25fps PAL) without descriptor
corruption, pointer clobbering, or instruction-level register faults.

Hardware Target: Sony Alpha ZV-E10 (CXD90045 / BIONZ X)
Authoritative Baseline: dumps/camera_2025/usr/usr/lib/
Output Directory: dumps/staged/uvc/binaries/patched/
"""

import argparse
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import struct
import sys
from typing import Any, Dict, List, Optional, Tuple

try:
    import capstone
    from capstone import arm
    HAS_CAPSTONE = True
except ImportError:
    HAS_CAPSTONE = False

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_DIR = REPO_ROOT / "dumps" / "camera_2025" / "usr" / "usr" / "lib"
DEFAULT_TARGET_DIR = REPO_ROOT / "dumps" / "staged" / "uvc" / "binaries" / "patched"


@dataclass(frozen=True)
class PatchEntry:
    """Represents a surgical byte-level patch entry."""
    offset: int
    expected_stock: bytes
    patched_bytes: bytes
    description: str


@dataclass
class PatchResult:
    """Result of applying patches to a single binary."""
    filename: str
    target_path: Path
    success: bool
    patches_applied: int
    sha256: str
    md5: str
    size: int
    errors: List[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Result of UVC descriptor and opcode validation."""
    valid: bool
    total_length: int
    expected_length: int
    details: List[str] = field(default_factory=list)


# Cryptographic Hash Database for Authoritative Stock Firmware
STOCK_METADATA: Dict[str, Dict[str, Any]] = {
    "libInfraUsbCmn.so": {
        "size": 94612,
        "md5": "31308976206a837f6f5c571992d2b499",
        "sha256": "af830315ce51c38b010995f2147d556286364323734f64b877fcc3bb1a916c02",
    },
    "libInfraStreamingUsb.so": {
        "size": 52524,
        "md5": "cde7a1b42c919706aa5f61aba5fc0d75",
        "sha256": "0a9448e364e8f014db02edc8e164470c70f2d2143ce5de74697e9ffba697cce8",
    },
}

# Cryptographic Hash Database for Hardened 1080p Patched Binaries
PATCHED_METADATA: Dict[str, Dict[str, Any]] = {
    "libInfraUsbCmn.so": {
        "size": 94612,
        "md5": "ac1961d23addcd53f4fe7210d074eac2",
        "sha256": "f089b3f66971edd6a3c5128ee7a8d295884fbf8dcc7bf51db94664998c509946",
    },
    "libInfraStreamingUsb.so": {
        "size": 52524,
        "md5": "5a0417693a3d9ed1786c4d0afc043d6e",
        "sha256": "e96fe28b9ac19b2ee918173f629d69a26c6f82766e28f4fd8fdfbb28d8a14259",
    },
}

# Canonical Exported Patch Tables
PATCHES: Dict[str, List[PatchEntry]] = {
    "libInfraUsbCmn.so": [
        PatchEntry(
            offset=0x12550,
            expected_stock=bytes([
                0x1E, 0x24, 0x07, 0x01, 0x00, 0x00, 0x05, 0xD0,
                0x02, 0x00, 0x00, 0xF9, 0x15, 0x00, 0x00, 0xF9,
                0x15, 0x00, 0x00, 0xE1, 0x00, 0x80, 0x1A, 0x06,
                0x00, 0x01, 0x80, 0x1A, 0x06, 0x00
            ]),
            patched_bytes=bytes([
                0x1E, 0x24, 0x07, 0x01, 0x00, 0x80, 0x07, 0x38,
                0x04, 0x00, 0xA3, 0xE1, 0x11, 0x00, 0xA3, 0xE1,
                0x11, 0x00, 0x00, 0xE1, 0x00, 0x80, 0x1A, 0x06,
                0x00, 0x01, 0x80, 0x1A, 0x06, 0x00
            ]),
            description="PAL VS_FRAME_MJPEG descriptor (1920x1080 @ 25fps, 300 Mbps)",
        ),
        PatchEntry(
            offset=0x1263E,
            expected_stock=bytes([
                0x1E, 0x24, 0x07, 0x01, 0x00, 0x00, 0x05, 0xD0,
                0x02, 0x00, 0x00, 0x5E, 0x1A, 0x00, 0x00, 0x5E,
                0x1A, 0x00, 0x00, 0xE1, 0x00, 0x15, 0x16, 0x05,
                0x00, 0x01, 0x15, 0x16, 0x05, 0x00
            ]),
            patched_bytes=bytes([
                0x1E, 0x24, 0x07, 0x01, 0x00, 0x80, 0x07, 0x38,
                0x04, 0x00, 0xA3, 0xE1, 0x11, 0x00, 0xA3, 0xE1,
                0x11, 0x00, 0x00, 0xE1, 0x00, 0x15, 0x16, 0x05,
                0x00, 0x01, 0x15, 0x16, 0x05, 0x00
            ]),
            description="NTSC VS_FRAME_MJPEG descriptor (1920x1080 @ 30fps, 300 Mbps)",
        ),
    ],
    "libInfraStreamingUsb.so": [
        PatchEntry(
            offset=0x908A,
            expected_stock=bytes([0x4F, 0xF4, 0xA0, 0x62]),  # mov.w r2, #1280
            patched_bytes=bytes([0x4F, 0xF4, 0xF0, 0x62]),   # mov.w r2, #1920
            description="VideoEsManager::video_stream_start Width (r2 = 1920)",
        ),
    ],
}


def compute_hashes(data: bytes) -> Tuple[str, str]:
    """Compute (md5, sha256) hex digests for bytes."""
    md5 = hashlib.md5(data).hexdigest()
    sha256 = hashlib.sha256(data).hexdigest()
    return md5, sha256


def verify_stock_file(path: Path) -> Tuple[bool, str]:
    """Verify that a stock binary matches genuine factory hashes and size."""
    filename = path.name
    if filename not in STOCK_METADATA:
        return False, f"Unknown binary: {filename}"
    if not path.is_file():
        return False, f"File does not exist: {path}"

    data = path.read_bytes()
    expected = STOCK_METADATA[filename]

    if len(data) != expected["size"]:
        return False, f"Size mismatch for {filename}: got {len(data)}, expected {expected['size']}"

    md5, sha256 = compute_hashes(data)
    if md5 != expected["md5"]:
        return False, f"MD5 mismatch for {filename}: got {md5}, expected {expected['md5']}"
    if sha256 != expected["sha256"]:
        return False, f"SHA256 mismatch for {filename}: got {sha256}, expected {expected['sha256']}"

    return True, f"{filename} verified OK against genuine factory dump"


def validate_uvc_descriptors(data: bytes) -> ValidationResult:
    """
    Validate UVC descriptor hierarchies and registration table fields in libInfraUsbCmn.so.
    Ensures CS_INTERFACE wTotalLength == downstream descriptor byte sum.
    """
    details: List[str] = []
    if len(data) != 94612:
        return ValidationResult(False, 0, 61, [f"Invalid file size: {len(data)} (expected 94612)"])

    valid = True

    # Validate PAL Descriptor Cluster at 0x12537
    pal_base = 0x12537
    pal_hdr_len, pal_desc_type, pal_subtype, pal_num_fmt, pal_total_len = struct.unpack(
        "<BBBBH", data[pal_base:pal_base + 6]
    )
    if pal_desc_type != 0x24 or pal_subtype != 0x01:
        details.append(f"PAL VS_INPUT_HEADER type mismatch: type={pal_desc_type:#x}, subtype={pal_subtype:#x}")
        valid = False

    pal_fmt_len, pal_fmt_type, pal_fmt_subtype, pal_fmt_idx, pal_num_frames = struct.unpack(
        "<BBBBB", data[pal_base + 14:pal_base + 19]
    )
    pal_frame_len, pal_frame_type, pal_frame_subtype = struct.unpack(
        "<BBB", data[pal_base + 25:pal_base + 28]
    )
    pal_color_len, pal_color_type, pal_color_subtype = struct.unpack(
        "<BBB", data[pal_base + 55:pal_base + 58]
    )

    pal_sum = pal_hdr_len + pal_fmt_len + pal_frame_len + pal_color_len
    if pal_sum != pal_total_len:
        details.append(f"PAL descriptor byte sum ({pal_sum}) != wTotalLength ({pal_total_len})")
        valid = False
    else:
        details.append(f"PAL descriptor sum matches wTotalLength = {pal_total_len} (14 + 11 + 30 + 6 = 61)")

    # PAL Frame Dimensions & Bitrates
    pal_w, pal_h = struct.unpack("<HH", data[0x12555:0x12559])
    pal_min_br, pal_max_br = struct.unpack("<II", data[0x12559:0x12561])
    pal_interval = struct.unpack("<I", data[0x12565:0x12569])[0]
    if pal_w != 1920 or pal_h != 1080:
        details.append(f"PAL resolution mismatch: {pal_w}x{pal_h} (expected 1920x1080)")
        valid = False
    else:
        details.append(f"PAL frame resolution verified: {pal_w}x{pal_h} @ 25fps (interval {pal_interval})")

    # Validate NTSC Descriptor Cluster at 0x12625
    ntsc_base = 0x12625
    ntsc_hdr_len, ntsc_desc_type, ntsc_subtype, ntsc_num_fmt, ntsc_total_len = struct.unpack(
        "<BBBBH", data[ntsc_base:ntsc_base + 6]
    )
    if ntsc_desc_type != 0x24 or ntsc_subtype != 0x01:
        details.append(f"NTSC VS_INPUT_HEADER type mismatch: type={ntsc_desc_type:#x}, subtype={ntsc_subtype:#x}")
        valid = False

    ntsc_fmt_len, ntsc_fmt_type, ntsc_fmt_subtype, ntsc_fmt_idx, ntsc_num_frames = struct.unpack(
        "<BBBBB", data[ntsc_base + 14:ntsc_base + 19]
    )
    ntsc_frame_len, ntsc_frame_type, ntsc_frame_subtype = struct.unpack(
        "<BBB", data[ntsc_base + 25:ntsc_base + 28]
    )
    ntsc_color_len, ntsc_color_type, ntsc_color_subtype = struct.unpack(
        "<BBB", data[ntsc_base + 55:ntsc_base + 58]
    )

    ntsc_sum = ntsc_hdr_len + ntsc_fmt_len + ntsc_frame_len + ntsc_color_len
    if ntsc_sum != ntsc_total_len:
        details.append(f"NTSC descriptor byte sum ({ntsc_sum}) != wTotalLength ({ntsc_total_len})")
        valid = False
    else:
        details.append(f"NTSC descriptor sum matches wTotalLength = {ntsc_total_len} (14 + 11 + 30 + 6 = 61)")

    # NTSC Frame Dimensions & Bitrates
    ntsc_w, ntsc_h = struct.unpack("<HH", data[0x12643:0x12647])
    ntsc_min_br, ntsc_max_br = struct.unpack("<II", data[0x12647:0x1264F])
    ntsc_interval = struct.unpack("<I", data[0x12653:0x12657])[0]
    if ntsc_w != 1920 or ntsc_h != 1080:
        details.append(f"NTSC resolution mismatch: {ntsc_w}x{ntsc_h} (expected 1920x1080)")
        valid = False
    else:
        details.append(f"NTSC frame resolution verified: {ntsc_w}x{ntsc_h} @ 30fps (interval {ntsc_interval})")

    # Validate Registration Tables in .data.rel.ro
    pal_table_len = struct.unpack("<I", data[0x14AB8:0x14ABC])[0]
    pal_table_ptr = struct.unpack("<I", data[0x14ABC:0x14AC0])[0]
    ntsc_table_len = struct.unpack("<I", data[0x14DB0:0x14DB4])[0]
    ntsc_table_ptr = struct.unpack("<I", data[0x14DB4:0x14DB8])[0]

    tables_ok = True
    if pal_table_len != 61:
        details.append(f"PAL registration table length at 0x14AB8 is {pal_table_len} (expected 61)")
        valid = False
        tables_ok = False
    if pal_table_ptr != 0x00012537:
        details.append(f"PAL registration table pointer corrupted at 0x14ABC: {pal_table_ptr:#x}")
        valid = False
        tables_ok = False

    if ntsc_table_len != 61:
        details.append(f"NTSC registration table length at 0x14DB0 is {ntsc_table_len} (expected 61)")
        valid = False
        tables_ok = False
    if ntsc_table_ptr != 0x00012625:
        details.append(f"NTSC registration table pointer corrupted at 0x14DB4: {ntsc_table_ptr:#x}")
        valid = False
        tables_ok = False

    if tables_ok:
        details.append("Registration tables verified intact (PAL: 0x14AB8=61, NTSC: 0x14DB0=61, pointers preserved)")
    else:
        details.append("Registration table validation failed: corrupted lengths or pointers")

    return ValidationResult(
        valid=valid,
        total_length=pal_total_len,
        expected_length=61,
        details=details,
    )


def validate_instruction_patch(data: bytes, offset: int = 0x908A) -> bool:
    """
    Validate that the patched instruction at offset is a valid Thumb-2 'mov.w r2, #1920'
    instruction preserving AAPCS callee-saved registers.
    """
    if len(data) != 52524:
        return False

    raw_chunk = data[offset:offset + 4]

    # Guard against halfword endianness inversion bug
    if raw_chunk == bytes([0xF0, 0x62, 0x4F, 0xF4]):
        return False

    if not HAS_CAPSTONE:
        # Fallback to direct byte comparison if capstone is absent
        return raw_chunk == bytes([0x4F, 0xF4, 0xF0, 0x62])

    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
    md.detail = True
    insns = list(md.disasm(raw_chunk, offset))

    if len(insns) != 1:
        return False

    insn = insns[0]
    if insn.mnemonic not in ("mov.w", "movw"):
        return False

    # Check operands: first operand r2, second operand 1920 (0x780)
    if len(insn.operands) != 2:
        return False
    op0, op1 = insn.operands[0], insn.operands[1]
    if op0.type != arm.ARM_OP_REG or op0.reg != arm.ARM_REG_R2:
        return False
    if op1.type != arm.ARM_OP_IMM or op1.imm != 1920:
        return False

    # Guardrail: Ensure no callee-saved registers (r4-r11, sp, lr) are modified
    callee_saved = {
        arm.ARM_REG_R4, arm.ARM_REG_R5, arm.ARM_REG_R6, arm.ARM_REG_R7,
        arm.ARM_REG_R8, arm.ARM_REG_R9, arm.ARM_REG_R10, arm.ARM_REG_R11,
        arm.ARM_REG_SP, arm.ARM_REG_LR,
    }
    regs_read, regs_written = insn.regs_access()
    if any(reg in callee_saved for reg in regs_written):
        return False

    return True


def apply_patches(
    source_dir: Optional[Path] = None,
    target_dir: Optional[Path] = None,
    patches: Optional[Dict[str, List[PatchEntry]]] = None,
    force: bool = False,
    validate: bool = True,
) -> Dict[str, Any]:
    """
    Apply surgical UVC patches to stock firmware binaries.

    Args:
        source_dir: Path to genuine stock binaries. Defaults to dumps/camera_2025/usr/usr/lib.
        target_dir: Path to write patched binaries. Defaults to dumps/staged/uvc/binaries/patched.
        patches: Dictionary mapping binary filenames to lists of PatchEntry. Defaults to PATCHES.
        force: Overwrite existing target binaries without prompt.
        validate: Run post-patch Capstone and UVC descriptor verification.

    Returns:
        Dictionary with keys:
            "success": bool
            "results": Dict[str, PatchResult]
            "errors": List[str]
    """
    source_path = Path(source_dir) if source_dir else DEFAULT_SOURCE_DIR
    target_path = Path(target_dir) if target_dir else DEFAULT_TARGET_DIR
    patch_dict = patches if patches is not None else PATCHES

    overall_success = True
    results: Dict[str, PatchResult] = {}
    errors: List[str] = []

    target_path.mkdir(parents=True, exist_ok=True)

    for filename, entries in patch_dict.items():
        src_file = source_path / filename
        dst_file = target_path / filename
        file_errors: List[str] = []

        if not src_file.exists():
            msg = f"Stock source file not found: {src_file}"
            file_errors.append(msg)
            errors.append(msg)
            results[filename] = PatchResult(
                filename=filename,
                target_path=dst_file,
                success=False,
                patches_applied=0,
                sha256="",
                md5="",
                size=0,
                errors=file_errors,
            )
            overall_success = False
            continue

        # Pre-flight stock verification
        stock_ok, stock_msg = verify_stock_file(src_file)
        if not stock_ok:
            file_errors.append(f"Stock verification failed: {stock_msg}")
            errors.append(f"{filename}: {stock_msg}")
            results[filename] = PatchResult(
                filename=filename,
                target_path=dst_file,
                success=False,
                patches_applied=0,
                sha256="",
                md5="",
                size=0,
                errors=file_errors,
            )
            overall_success = False
            continue

        data = bytearray(src_file.read_bytes())
        patches_applied = 0

        for entry in entries:
            end_offset = entry.offset + len(entry.expected_stock)
            actual_stock = data[entry.offset:end_offset]

            if actual_stock != entry.expected_stock:
                msg = (
                    f"Offset {entry.offset:#x} in {filename} mismatch: "
                    f"got {actual_stock.hex()}, expected {entry.expected_stock.hex()}"
                )
                file_errors.append(msg)
                errors.append(msg)
                continue

            data[entry.offset:entry.offset + len(entry.patched_bytes)] = entry.patched_bytes
            patches_applied += 1

        final_bytes = bytes(data)
        md5, sha256 = compute_hashes(final_bytes)

        # Post-patch validation
        if validate:
            if filename == "libInfraUsbCmn.so":
                val = validate_uvc_descriptors(final_bytes)
                if not val.valid:
                    file_errors.extend(val.details)
                    errors.extend(val.details)
            elif filename == "libInfraStreamingUsb.so":
                insn_ok = validate_instruction_patch(final_bytes, 0x908A)
                if not insn_ok:
                    msg = "Instruction patch validation failed at 0x908A (invalid opcode or register clobber)"
                    file_errors.append(msg)
                    errors.append(msg)

        # Match against expected patched hash if known
        if filename in PATCHED_METADATA:
            expected_patched = PATCHED_METADATA[filename]
            if len(final_bytes) != expected_patched["size"]:
                file_errors.append(f"Output size mismatch: {len(final_bytes)} != {expected_patched['size']}")
            if md5 != expected_patched["md5"]:
                file_errors.append(f"Patched MD5 mismatch: {md5} != {expected_patched['md5']}")
            if sha256 != expected_patched["sha256"]:
                file_errors.append(f"Patched SHA-256 mismatch: {sha256} != {expected_patched['sha256']}")

        file_success = (len(file_errors) == 0 and patches_applied == len(entries))
        if not file_success:
            overall_success = False

        if file_success or force:
            dst_file.write_bytes(final_bytes)

        results[filename] = PatchResult(
            filename=filename,
            target_path=dst_file,
            success=file_success,
            patches_applied=patches_applied,
            sha256=sha256,
            md5=md5,
            size=len(final_bytes),
            errors=file_errors,
        )

    return {
        "success": overall_success,
        "results": results,
        "errors": errors,
    }


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint for standalone patch generation and verification."""
    parser = argparse.ArgumentParser(
        description="Surgical 1080p UVC Patch Generator for Sony ZV-E10",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-s", "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help=f"Directory containing stock binaries (default: {DEFAULT_SOURCE_DIR})",
    )
    parser.add_argument(
        "-t", "--target-dir",
        type=Path,
        default=DEFAULT_TARGET_DIR,
        help=f"Directory to output patched binaries (default: {DEFAULT_TARGET_DIR})",
    )
    parser.add_argument(
        "-d", "--dry-run",
        action="store_true",
        help="Simulate patching and display plan without writing to disk",
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Overwrite target binaries even if validation encounters warnings",
    )
    parser.add_argument(
        "-v", "--verify-only",
        action="store_true",
        help="Verify existing binaries in target directory without patching",
    )

    args = parser.parse_args(argv)

    print("================================================================================")
    print("  Sony Alpha ZV-E10 UVC 1080p Single-Shot Surgical Patch Generator")
    print("================================================================================")

    if args.verify_only:
        print(f"[*] Verifying patched binaries in {args.target_dir}...")
        all_ok = True
        for filename, expected in PATCHED_METADATA.items():
            fpath = args.target_dir / filename
            if not fpath.is_file():
                print(f"  [-] Missing target file: {fpath}")
                all_ok = False
                continue
            data = fpath.read_bytes()
            md5, sha256 = compute_hashes(data)
            size = len(data)
            if size != expected["size"] or md5 != expected["md5"] or sha256 != expected["sha256"]:
                print(f"  [-] Hash mismatch for {filename}:")
                print(f"      Size:   {size} (expected {expected['size']})")
                print(f"      MD5:    {md5} (expected {expected['md5']})")
                print(f"      SHA256: {sha256} (expected {expected['sha256']})")
                all_ok = False
            else:
                print(f"  [+] {filename}: VERIFIED OK (Size: {size}, MD5: {md5})")
                if filename == "libInfraUsbCmn.so":
                    val = validate_uvc_descriptors(data)
                    for det in val.details:
                        print(f"      • {det}")
                elif filename == "libInfraStreamingUsb.so":
                    insn_ok = validate_instruction_patch(data, 0x908A)
                    print(f"      • Instruction at 0x908A verified: {insn_ok}")
        return 0 if all_ok else 1

    if args.dry_run:
        print("[*] DRY-RUN MODE: Verifying stock binaries and displaying planned patches...")
        for filename, entries in PATCHES.items():
            src = args.source_dir / filename
            stock_ok, stock_msg = verify_stock_file(src)
            status = "[OK]" if stock_ok else "[FAILED]"
            print(f"  {status} Stock file {filename}: {stock_msg}")
            for entry in entries:
                print(f"       -> Patch at offset {entry.offset:#06x} ({len(entry.patched_bytes)} B): {entry.description}")
        return 0

    print(f"[*] Applying surgical 1080p patches:")
    print(f"    Source: {args.source_dir}")
    print(f"    Target: {args.target_dir}")
    print("--------------------------------------------------------------------------------")

    result = apply_patches(
        source_dir=args.source_dir,
        target_dir=args.target_dir,
        patches=PATCHES,
        force=args.force,
        validate=True,
    )

    for filename, presult in result["results"].items():
        tag = "[SUCCESS]" if presult.success else "[FAILURE]"
        print(f"{tag} {filename}: {presult.patches_applied} patches applied")
        print(f"         Output:  {presult.target_path}")
        print(f"         Size:    {presult.size} bytes")
        print(f"         MD5:     {presult.md5}")
        print(f"         SHA-256: {presult.sha256}")
        if presult.errors:
            for err in presult.errors:
                print(f"         Error: {err}")

    print("--------------------------------------------------------------------------------")
    if result["success"]:
        print("[+] All target binaries successfully patched and validated!")
        return 0
    else:
        print("[-] One or more patch operations failed. Check logs above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
