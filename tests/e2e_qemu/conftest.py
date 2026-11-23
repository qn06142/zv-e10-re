"""Shared pytest configuration and deferred fixtures for tests/e2e_qemu/.

All `emulator.*` imports and built-binary checks are deferred inside fixtures
so `pytest --collect-only` and `pytest -m "not e2e_qemu"` work cleanly at any
milestone without modifying `pytest.ini`.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Iterator

import pytest

from tests.e2e_qemu.helpers import (
    DUMPS_DIR,
    QEMU_BIN,
    REPO_ROOT,
    ZVE10_QEMU_DIR,
    enforce_no_qemu_leak,
    list_qemu_pids,
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def pytest_configure(config: pytest.Config) -> None:
    """Register E2E markers locally without touching pytest.ini."""
    markers = (
        "e2e_qemu: Opaque-box E2E tests exercising pmca-re ZV-E10 QEMU emulation",
        "tier1: Tier 1 isolated happy-path feature tests",
        "tier2: Tier 2 boundary, corner, and error-handling tests",
        "tier3: Tier 3 pairwise cross-feature integration tests",
        "tier4: Tier 4 full real-world end-to-end application scenarios",
        "r3_guard: Read-only integrity verification for zve10-qemu and .local/dumps/",
    )
    for marker in markers:
        config.addinivalue_line("markers", marker)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def dumps_dir() -> Path:
    if not DUMPS_DIR.is_dir():
        pytest.fail(f"Required read-only dumps directory missing: {DUMPS_DIR}")
    return DUMPS_DIR


@pytest.fixture(scope="session")
def zve10_qemu_dir() -> Path:
    if not ZVE10_QEMU_DIR.is_dir():
        pytest.fail(f"Required read-only reference repo missing: {ZVE10_QEMU_DIR}")
    return ZVE10_QEMU_DIR


@pytest.fixture
def qemu_bin_path() -> Path:
    """Return path to built qemu-system-arm.exe, failing with M1 diagnostic if absent."""
    if not QEMU_BIN.is_file():
        pytest.fail(
            f"M1 missing: built QEMU binary not found at {QEMU_BIN}. "
            "Build QEMU 11.1.2 (emulator.build_qemu) before running E2E tests."
        )
    return QEMU_BIN


@pytest.fixture
def build_qemu_mod():
    """Import emulator.build_qemu lazily, failing with M1 diagnostic if missing."""
    try:
        return importlib.import_module("emulator.build_qemu")
    except ImportError as exc:
        pytest.fail(f"M1 missing: cannot import emulator.build_qemu ({exc})")


@pytest.fixture
def qemu_runner_cls():
    """Import QemuRunner and BootResult lazily from emulator.runner."""
    try:
        mod = importlib.import_module("emulator.runner")
    except ImportError as exc:
        pytest.fail(f"M1 missing: cannot import emulator.runner ({exc})")
    runner_cls = getattr(mod, "QemuRunner", None)
    boot_result_cls = getattr(mod, "BootResult", None)
    if runner_cls is None or boot_result_cls is None:
        pytest.fail(
            "M1 interface mismatch: emulator.runner must export QemuRunner and BootResult"
        )
    return runner_cls, boot_result_cls


@pytest.fixture
def boot_stub_mod():
    """Import emulator.boot_stub lazily, failing with M1 diagnostic if missing."""
    try:
        return importlib.import_module("emulator.boot_stub")
    except ImportError as exc:
        pytest.fail(f"M1 missing: cannot import emulator.boot_stub ({exc})")


@pytest.fixture
def storage_mod():
    """Import emulator.storage lazily, failing with M2 diagnostic if missing."""
    try:
        return importlib.import_module("emulator.storage")
    except ImportError as exc:
        pytest.fail(f"M2 missing: cannot import emulator.storage ({exc})")


@pytest.fixture
def qemu_workdir(tmp_path: Path) -> Iterator[Path]:
    """Provide isolated per-test workdir and ensure no QEMU processes leak."""
    before_pids = list_qemu_pids()
    workdir = tmp_path / "qemu_work"
    (workdir / "artifacts").mkdir(parents=True, exist_ok=True)
    (workdir / "captures").mkdir(parents=True, exist_ok=True)
    try:
        yield workdir
    finally:
        enforce_no_qemu_leak(baseline_pids=before_pids)
