"""
Offline verification of the concrete Sony live frame source backend.
Tests real compiled C structures, ABI contracts, lease lifecycles, timeout caps,
error fallbacks, and verifies zero NEON instructions for ARM Cortex-A5.
"""

from pathlib import Path
import subprocess
import tempfile
import pytest
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB
from capstone.arm import ARM_GRP_NEON

SRC_DIR = Path(__file__).resolve().parent
REPO_ROOT = SRC_DIR.parents[2]


def test_sony_backend_native_execution():
    """Compile and execute the native Sony backend test harness."""
    with tempfile.TemporaryDirectory(prefix="raw-sony-test-") as directory:
        exe = Path(directory) / "test_raw_live_sony.exe"
        cmd = [
            "gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
            "-DRAW_FRAME_CONVERSION_ONLY",
            "-DSONY_ENABLE_LEGACY_TEST_FIXTURES",
            "-fno-tree-vectorize", "-fno-tree-slp-vectorize",
            f"-I{SRC_DIR}",
            str(SRC_DIR / "test_raw_live_sony.c"),
            str(SRC_DIR / "raw_live_sony.c"),
            str(SRC_DIR / "raw_live_source.c"),
            str(SRC_DIR / "raw_frame_source.c"),
            "-o", str(exe)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, f"Compilation failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"

        run_res = subprocess.run([str(exe)], capture_output=True, text=True)
        assert run_res.returncode == 0, f"Execution failed:\nSTDOUT:\n{run_res.stdout}\nSTDERR:\n{run_res.stderr}"
        assert "ALL SONY LIVE BACKEND TESTS PASSED cleanly! (cases=7)" in run_res.stdout


def test_arm_cortex_a5_compilation_and_zero_neon():
    """
    Cross-compile raw_live_sony.c with arm-none-eabi-gcc targeting Cortex-A5 (VFPv4-D16, no NEON).
    Disassemble the compiled ELF object using Capstone and verify that ZERO NEON instructions exist.
    """
    arm_gcc = "arm-none-eabi-gcc"
    with tempfile.TemporaryDirectory(prefix="raw-sony-arm-") as directory:
        obj = Path(directory) / "raw_live_sony.o"
        cmd = [
            arm_gcc,
            "-mcpu=cortex-a5",
            "-marm",
            "-mfpu=vfpv4-d16",
            "-fno-tree-vectorize",
            "-fno-tree-slp-vectorize",
            "-mfloat-abi=soft",
            "-O2",
            "-fPIC",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-DRAW_FRAME_CONVERSION_ONLY",
            "-DSONY_ENABLE_LEGACY_TEST_FIXTURES",
            "-DRAW_LIVE_TARGET_ARM",
            f"-I{SRC_DIR}",
            "-c", str(SRC_DIR / "raw_live_sony.c"),
            "-o", str(obj)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, f"ARM GCC compilation failed:\n{res.stderr}"

        # Inspect ELF binary with Capstone
        neon_count = 0
        total_instructions = 0
        with open(obj, "rb") as f:
            elf = ELFFile(f)
            text_sec = elf.get_section_by_name(".text")
            assert text_sec is not None, "Missing .text section in raw_live_sony.o"
            code_bytes = text_sec.data()
            assert len(code_bytes) > 0, ".text section is empty"

            md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
            md.detail = True
            for insn in md.disasm(code_bytes, 0):
                total_instructions += 1
                if ARM_GRP_NEON in insn.groups:
                    neon_count += 1

        assert total_instructions > 0, "No instructions disassembled"
        assert neon_count == 0, f"VIOLATION: Found {neon_count} NEON instructions in raw_live_sony.o!"
