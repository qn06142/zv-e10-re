"""Run bounded lease/copy tests; these use synthetic input, not camera IPC."""
from pathlib import Path
import subprocess
import tempfile


def test_lease_pipeline():
    src = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="raw-live-test-") as directory:
        exe = Path(directory) / "test_raw_live_source.exe"
        subprocess.run([
            "gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
            "-DRAW_FRAME_CONVERSION_ONLY", "-fno-tree-vectorize", "-fno-tree-slp-vectorize",
            "-I", str(src), str(src / "test_raw_live_source.c"),
            str(src / "raw_live_source.c"), str(src / "raw_frame_source.c"), "-o", str(exe)
        ], check=True, capture_output=True, text=True)
        result = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
        assert "cases=32" in result.stdout
