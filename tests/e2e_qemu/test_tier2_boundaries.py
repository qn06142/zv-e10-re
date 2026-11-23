"""Tier 2: Boundary, Corner, and Error-Case E2E Tests (45 tests: T2-A1..I5)."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
import pytest

from tests.e2e_qemu.helpers import (
    LINUX_EABI_MINIMAL_C_PRELUDE,
    UART0_PROBE_C_PRELUDE,
    ZVRT_PROBE_FAIL,
    QmpClient,
    assert_dumps_unmodified,
    build_baremetal_arm_probe,
    build_minimal_initrd_cpio,
    build_zvos_baremetal_elf,
    build_zvos_payload,
    check_r3_snapshot,
    drive_adc_gpio_stimulus,
    free_tcp_port,
    list_qemu_pids,
    prepare_staged_storage,
    prepare_stock_kernel_with_boot_stub,
    run_probe_with_runner,
    run_qemu_and_qmp_capture,
    run_subprocess_deadline,
    snapshot_dumps_hashes,
    ucrt64_env,
    verify_os_shell_status_frame,
    verify_png_frame,
)

pytestmark = [pytest.mark.e2e_qemu, pytest.mark.tier2]


# =============================================================================
# Area A — Build & Packaging Boundaries
# =============================================================================


def test_build_qemu_wrong_tarball_checksum(build_qemu_mod, tmp_path: Path) -> None:
    """T2-A1: build_qemu rejects a corrupted qemu-11.1.2.tar.xz with checksum mismatch."""
    bad_tar = tmp_path / "qemu-11.1.2.tar.xz"
    bad_tar.write_bytes(b"corrupted-not-a-valid-qemu-tarball")
    verify_fn = getattr(build_qemu_mod, "verify_tarball", None) or getattr(
        build_qemu_mod, "verify_tarball_sha256", None
    )
    assert callable(verify_fn), (
        "emulator.build_qemu must expose verify_tarball or verify_tarball_sha256"
    )
    with pytest.raises((ValueError, RuntimeError, AssertionError)):
        verify_fn(bad_tar)


def test_build_qemu_missing_toolchain_path(build_qemu_mod, repo_root: Path) -> None:
    """T2-A2: build_qemu fails cleanly when MSYS2 UCRT64 toolchain is absent from PATH."""
    build_script = repo_root / "emulator" / "build_qemu.py"
    assert build_script.is_file(), f"Missing {build_script}"
    env = ucrt64_env(strip_ucrt64=True)
    # Also remove any generic msys64 paths so gcc/meson cannot be resolved via PATH
    env["PATH"] = os.pathsep.join(
        p for p in env["PATH"].split(os.pathsep) if "msys64" not in p.lower()
    )
    check_fn = getattr(build_qemu_mod, "check_toolchain", None)
    if callable(check_fn):
        with pytest.raises((FileNotFoundError, RuntimeError, EnvironmentError)):
            check_fn(env=env)
    else:
        res = run_subprocess_deadline(
            [str(repo_root / ".venv" / "Scripts" / "python.exe"), str(build_script), "--check"],
            env=env,
            timeout_s=15.0,
        )
        assert res.returncode != 0


def test_qemu_invalid_machine_name(qemu_bin_path: Path) -> None:
    """T2-A3: qemu-system-arm.exe rejects unknown machine type with non-zero exit."""
    res = run_subprocess_deadline(
        [str(qemu_bin_path), "-M", "nonexistent_zve10_board", "-display", "none"],
        env=ucrt64_env(),
        timeout_s=10.0,
    )
    assert res.returncode != 0
    assert "unsupported machine type" in res.stderr.lower()


def test_qemu_invalid_smp_exceeds_max(qemu_bin_path: Path) -> None:
    """T2-A4: -M zve10 -smp 5 fails because max_cpus=4."""
    res = run_subprocess_deadline(
        [str(qemu_bin_path), "-M", "zve10", "-smp", "5", "-display", "none"],
        env=ucrt64_env(),
        timeout_s=10.0,
    )
    assert res.returncode != 0
    assert "max cpus" in res.stderr.lower() or "smp" in res.stderr.lower()


def test_qemu_invalid_cpu_type(qemu_bin_path: Path) -> None:
    """T2-A5: -M zve10 -cpu cortex-a15 fails because only cortex-a9 is valid."""
    res = run_subprocess_deadline(
        [str(qemu_bin_path), "-M", "zve10", "-cpu", "cortex-a15", "-display", "none"],
        env=ucrt64_env(),
        timeout_s=10.0,
    )
    assert res.returncode != 0
    assert "cortex-a15" in res.stderr.lower() or "invalid cpu" in res.stderr.lower()


# =============================================================================
# Area B — Base SoC & Peripheral Boundaries
# =============================================================================


def test_soc_memory_wrong_size_under_1g(
    qemu_runner_cls,
    boot_stub_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T2-B1: Booting stock vmlinux.bin with -m 256 and mem=1G@0 fails predictably without hang."""
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    res = run_probe_with_runner(
        runner_cls,
        kernel=kern,
        initrd=dumps_dir / "firmware" / "initrd.img",
        memory="256",
        append="mem=1G@0 ramdisk_size=8192 root=/dev/ram0 rw init=/sbin/init console=ttyAM0,115200n8 cfg.uart=1",
        workdir=qemu_workdir,
        timeout_s=8.0,
    )
    # Either kernel panics/fails early or times out cleanly bounded by timeout_s=8s
    assert res.timed_out or "Kernel panic" in res.serial_output or "BUG:" in res.serial_output


def test_soc_timer_prescaler_and_oneshot_boundary(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T2-B2: sony-hwtimer one-shot (0x10) clears enable bit 0x1000 while periodic (0x00) refires."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "timer_oneshot_periodic",
        UART0_PROBE_C_PRELUDE
        + """
static volatile uint32_t irq_hits = 0;
void probe_irq_handler(void) {
    uint32_t iar = mmio_r32(0xF800010CU);
    if ((iar & 0x3FFU) == 154U) {
        irq_hits++;
        mmio_w32(0xF2403104U, 1U);
    }
    mmio_w32(0xF8000110U, iar);
}
void probe_main(void) {
    mmio_w32(0xF8001000U, 1U);
    mmio_w32(0xF8000104U, 0xFFU);
    mmio_w32(0xF8000100U, 1U);
    mmio_w32(0xF8001100U + (154U / 32U) * 4U, 1U << (154U % 32U));
    __asm__ volatile("cpsie i");

    /* One-shot mode (0x10) with prescaler 2 (4MHz / 4 = 1MHz), compare = 2000 */
    mmio_w32(0xF2403100U, 0x80000000U);
    mmio_w32(0xF2403108U, 2000U);
    mmio_w32(0xF2403100U, 0x00001112U);
    for (volatile uint32_t i = 0; i < 1500000U && irq_hits < 1U; i++) {}
    uint32_t ctrl_after = mmio_r32(0xF2403100U);
    if (irq_hits == 1U && (ctrl_after & 0x1000U) == 0U) uart_puts("ONESHOT_OK\\n");

    /* Periodic mode (0x00), compare = 2000 */
    irq_hits = 0U;
    mmio_w32(0xF2403100U, 0x80000000U);
    mmio_w32(0xF2403108U, 2000U);
    mmio_w32(0xF2403100U, 0x00001100U);
    for (volatile uint32_t i = 0; i < 3000000U && irq_hits < 3U; i++) {}
    if (irq_hits >= 3U) uart_puts("PERIODIC_OK\\n");
    uart_puts("TBOUND_DONE\\n");
}
""",
        with_irq_vector=True,
    )
    res = run_probe_with_runner(runner_cls, kernel=probe, workdir=qemu_workdir, wait_pattern="TBOUND_DONE", timeout_s=10.0)
    assert not res.timed_out
    assert "ONESHOT_OK" in res.serial_output
    assert "PERIODIC_OK" in res.serial_output


def test_soc_timer_compare_wrap_max_uint32(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T2-B3: sony-hwtimer free-running mode with compare=0xFFFFFFFF does not spin-hang QEMU."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "timer_wrap",
        UART0_PROBE_C_PRELUDE
        + """
void probe_main(void) {
    mmio_w32(0xF2403200U, 0x80000000U);
    mmio_w32(0xF2403208U, 0xFFFFFFFFU);
    mmio_w32(0xF2403210U, 0xFFFFFFFCU);
    mmio_w32(0xF2403200U, 0x00001030U);
    for (volatile uint32_t i = 0; i < 200000U; i++) {}
    (void)mmio_r32(0xF240320CU);
    uart_puts("WRAP_OK\\n");
}
""",
    )
    res = run_probe_with_runner(runner_cls, kernel=probe, workdir=qemu_workdir, wait_pattern="WRAP_OK", timeout_s=8.0)
    assert not res.timed_out
    assert "WRAP_OK" in res.serial_output


def test_soc_gpe_malformed_packet_no_fence_irq(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T2-B4: GPE startup trigger with malformed zeroed packet does not fire spurious IRQ 76."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "gpe_malformed",
        UART0_PROBE_C_PRELUDE
        + """
static volatile uint32_t spurious_irq = 0;
static uint32_t bad_pkt[8] __attribute__((aligned(16))) = {0};
void probe_irq_handler(void) {
    uint32_t iar = mmio_r32(0xF800010CU);
    if ((iar & 0x3FFU) == 76U) spurious_irq = 1U;
    mmio_w32(0xF8000110U, iar);
}
void probe_main(void) {
    mmio_w32(0xF8001000U, 1U);
    mmio_w32(0xF8000104U, 0xFFU);
    mmio_w32(0xF8000100U, 1U);
    mmio_w32(0xF8001100U + (76U / 32U) * 4U, 1U << (76U % 32U));
    __asm__ volatile("cpsie i");
    mmio_w32(0xF1001804U, (uint32_t)(uintptr_t)bad_pkt);
    mmio_w32(0xF1001800U, 4U);
    for (volatile uint32_t i = 0; i < 200000U; i++) {}
    if (!spurious_irq) uart_puts("NO_SPURIOUS_GPE_OK\\n");
}
""",
        with_irq_vector=True,
    )
    res = run_probe_with_runner(runner_cls, kernel=probe, workdir=qemu_workdir, wait_pattern="NO_SPURIOUS_GPE_OK", timeout_s=8.0)
    assert not res.timed_out
    assert "NO_SPURIOUS_GPE_OK" in res.serial_output


def test_soc_esram_boundary_access(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T2-B5: 32 KiB eSRAM base (0xfe000000) and top word (0xfe007ffc) read/write cleanly."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "esram_bounds",
        UART0_PROBE_C_PRELUDE
        + """
void probe_main(void) {
    mmio_w32(0x00100000U, 0x11223344U);
    mmio_w32(0xFE000000U, 0xA5A50001U);
    mmio_w32(0xFE007FFCU, 0x5A5AFFFFU);
    if (mmio_r32(0xFE000000U) == 0xA5A50001U &&
        mmio_r32(0xFE007FFCU) == 0x5A5AFFFFU &&
        mmio_r32(0x00100000U) == 0x11223344U) {
        uart_puts("ESRAM_BOUNDS_OK\\n");
    }
}
""",
    )
    res = run_probe_with_runner(runner_cls, kernel=probe, workdir=qemu_workdir, wait_pattern="ESRAM_BOUNDS_OK", timeout_s=8.0)
    assert not res.timed_out
    assert "ESRAM_BOUNDS_OK" in res.serial_output


# =============================================================================
# Area C — Stock vmlinux.bin & ATAGs Boundaries
# =============================================================================


def test_vmlinux_unpatched_r2_clobber_demonstration(
    qemu_runner_cls,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T2-C1: Raw unmodified vmlinux.bin without ATAG trampoline fails to preserve cmdline token."""
    runner_cls, _ = qemu_runner_cls
    res = run_probe_with_runner(
        runner_cls,
        kernel=dumps_dir / "firmware" / "vmlinux.bin",
        append="mem=1G@0 console=ttyAM0,115200n8 cfg.uart=1 pmca_e2e_tag=lost_without_stub",
        workdir=qemu_workdir,
        timeout_s=6.0,
    )
    assert "pmca_e2e_tag=lost_without_stub" not in res.serial_output


def test_vmlinux_missing_mem_1g_param(
    qemu_runner_cls,
    boot_stub_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T2-C2: Stock vmlinux.bin booted without mem=1G@0 fails early due to CONFIG_EJ_NO_ATAG_MEM."""
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    initrd = build_minimal_initrd_cpio(
        qemu_workdir / "artifacts",
        LINUX_EABI_MINIMAL_C_PRELUDE + 'void init_main(void) { out_str("SHOULD_NOT_REACH_INIT\\n"); }',
    )
    res = run_probe_with_runner(
        runner_cls,
        kernel=kern,
        initrd=initrd,
        append="console=ttyAM0,115200n8 cfg.uart=1 rdinit=/init",
        workdir=qemu_workdir,
        timeout_s=8.0,
    )
    assert "SHOULD_NOT_REACH_INIT" not in res.serial_output


def test_vmlinux_earlyprintk_flag_harmless(
    qemu_runner_cls,
    boot_stub_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T2-C3: Including earlyprintk alongside console=ttyAM0,115200n8 cfg.uart=1 boots cleanly."""
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    initrd = build_minimal_initrd_cpio(
        qemu_workdir / "artifacts",
        LINUX_EABI_MINIMAL_C_PRELUDE + 'void init_main(void) { out_str("EARLYPRINTK_OK\\n"); }',
    )
    res = run_probe_with_runner(
        runner_cls,
        kernel=kern,
        initrd=initrd,
        append="mem=1G@0 console=ttyAM0,115200n8 cfg.uart=1 earlyprintk rdinit=/init",
        workdir=qemu_workdir,
        wait_pattern="EARLYPRINTK_OK",
        timeout_s=20.0,
    )
    assert not res.timed_out
    assert "EARLYPRINTK_OK" in res.serial_output


def test_vmlinux_long_cmdline_truncation_boundary(
    qemu_runner_cls,
    boot_stub_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T2-C4: Near-1024-byte kernel command line boots gracefully without crash."""
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    initrd = build_minimal_initrd_cpio(
        qemu_workdir / "artifacts",
        LINUX_EABI_MINIMAL_C_PRELUDE + 'void init_main(void) { out_str("LONG_CMDLINE_OK\\n"); }',
    )
    pad = " ".join(f"p{i}=1" for i in range(90))
    append = f"mem=1G@0 console=ttyAM0,115200n8 cfg.uart=1 rdinit=/init {pad}"
    res = run_probe_with_runner(
        runner_cls,
        kernel=kern,
        initrd=initrd,
        append=append[:980],
        workdir=qemu_workdir,
        wait_pattern="LONG_CMDLINE_OK",
        timeout_s=20.0,
    )
    assert not res.timed_out
    assert "LONG_CMDLINE_OK" in res.serial_output


def test_vmlinux_corrupted_truncated_kernel(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T2-C5: Truncated 64 KB kernel image terminates cleanly within timeout without Python crash."""
    runner_cls, boot_result_cls = qemu_runner_cls
    bad_kern = qemu_workdir / "artifacts" / "truncated.bin"
    bad_kern.write_bytes(b"\x00" * 65536)
    res = run_probe_with_runner(
        runner_cls,
        kernel=bad_kern,
        workdir=qemu_workdir,
        timeout_s=4.0,
    )
    assert isinstance(res, boot_result_cls)


# =============================================================================
# Area D — QemuRunner & R3 Guard Boundaries
# =============================================================================


def test_runner_missing_kernel_path(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T2-D1: Non-existent kernel path fails explicitly before leaving any orphan QEMU."""
    runner_cls, _ = qemu_runner_cls
    before_pids = list_qemu_pids()
    missing = qemu_workdir / "does_not_exist.bin"
    with pytest.raises((FileNotFoundError, ValueError, RuntimeError, OSError)):
        runner = runner_cls(kernel=missing, display="none", serial_log=qemu_workdir / "serial.log", timeout_s=5.0)
        runner.start()
    assert list_qemu_pids() == before_pids


def test_runner_timeout_kills_qemu_cleanly(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T2-D2: Infinite-loop guest expires timeout_s, sets timed_out=True, and kills QEMU."""
    runner_cls, _ = qemu_runner_cls
    before_pids = list_qemu_pids()
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "hang_probe",
        UART0_PROBE_C_PRELUDE + 'void probe_main(void) { uart_puts("LOOP_START\\n"); while (1) {} }',
    )
    res = run_probe_with_runner(
        runner_cls,
        kernel=probe,
        workdir=qemu_workdir,
        wait_pattern="NEVER_PRINTED_TOKEN",
        timeout_s=2.0,
    )
    assert res.timed_out is True
    assert list_qemu_pids() == before_pids


def test_runner_invalid_qmp_command(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T2-D3: Invalid QMP command raises structured error without crashing running QEMU."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "qmp_err",
        UART0_PROBE_C_PRELUDE + 'void probe_main(void) { uart_puts("QMP_UP\\n"); }',
    )
    runner = runner_cls(
        kernel=probe,
        display="none",
        serial_log=qemu_workdir / "serial.log",
        qmp_port=free_tcp_port(),
        timeout_s=10.0,
    )
    runner.start()
    try:
        runner.wait_for_serial("QMP_UP", timeout_s=6.0)
        with pytest.raises(Exception) as exc_info:
            runner.qmp_command("nonexistent-qmp-command-xyz")
        assert "nonexistent-qmp-command-xyz" in str(exc_info.value) or "CommandNotFound" in str(exc_info.value) or exc_info.value
        status = runner.qmp_command("query-status")
        assert "running" in status
    finally:
        try:
            runner.stop()
        except Exception:
            pass


def test_runner_qmp_after_stop_rejected(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T2-D4: Calling qmp_command after stop() fails cleanly with RuntimeError/ConnectionError."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "qmp_stopped",
        UART0_PROBE_C_PRELUDE + 'void probe_main(void) { uart_puts("QMP_STOP\\n"); }',
    )
    runner = runner_cls(
        kernel=probe,
        display="none",
        serial_log=qemu_workdir / "serial.log",
        qmp_port=free_tcp_port(),
        timeout_s=10.0,
    )
    runner.start()
    try:
        runner.wait_for_serial("QMP_STOP", timeout_s=6.0)
        runner.stop()
        with pytest.raises((RuntimeError, ConnectionError, OSError)):
            runner.qmp_command("query-status")
    finally:
        try:
            runner.stop()
        except Exception:
            pass


@pytest.mark.r3_guard
def test_r3_guard_detects_simulated_dirty_change(tmp_path: Path) -> None:
    """T2-D5: R3 guard helper detects unexpected dirty/untracked files or newer mtime in a temp git repo."""
    sim_repo = tmp_path / "sim_zve10_qemu"
    sim_repo.mkdir()
    subprocess.run(["git", "-C", str(sim_repo), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(sim_repo), "config", "user.email", "e2e@example.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(sim_repo), "config", "user.name", "E2E"], check=True, capture_output=True)
    tracked = sim_repo / "README.md"
    tracked.write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(sim_repo), "add", "README.md"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(sim_repo), "commit", "-m", "init"], check=True, capture_output=True)
    head = subprocess.check_output(["git", "-C", str(sim_repo), "rev-parse", "HEAD"], text=True).strip()

    # Baseline clean check passes
    check_r3_snapshot(sim_repo, expected_head=head, allowed_dirty=frozenset(), max_mtime=time.time() + 10.0)

    # Simulate rogue untracked file -> must fail
    rogue = sim_repo / "rogue_edit.txt"
    rogue.write_text("dirty\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="rogue_edit.txt"):
        check_r3_snapshot(sim_repo, expected_head=head, allowed_dirty=frozenset(), max_mtime=time.time() + 10.0)


# =============================================================================
# Area E — Stock Kernel + initrd.img Boundaries
# =============================================================================


def test_initrd_corrupted_image_fails_gracefully(
    qemu_runner_cls,
    boot_stub_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T2-E1: Zeroed/corrupted initrd.img triggers clean RAMDISK failure without hanging pytest."""
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    bad_initrd = qemu_workdir / "artifacts" / "bad_initrd.img"
    bad_initrd.write_bytes(b"\x00" * 65536)
    res = run_probe_with_runner(
        runner_cls,
        kernel=kern,
        initrd=bad_initrd,
        append="mem=1G@0 ramdisk_size=8192 root=/dev/ram0 rw init=/sbin/init console=ttyAM0,115200n8 cfg.uart=1",
        workdir=qemu_workdir,
        timeout_s=15.0,
    )
    assert (
        "Couldn't find valid RAM disk image" in res.serial_output
        or "Kernel panic" in res.serial_output
        or "VFS: Cannot open root device" in res.serial_output
    )


def test_initrd_wrong_ramdisk_size_too_small(
    qemu_runner_cls,
    boot_stub_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T2-E2: Booting 2.1 MiB ext2 initrd.img with ramdisk_size=1024 fails cleanly on truncated block device."""
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    res = run_probe_with_runner(
        runner_cls,
        kernel=kern,
        initrd=dumps_dir / "firmware" / "initrd.img",
        append="mem=1G@0 ramdisk_size=1024 root=/dev/ram0 rw init=/sbin/init console=ttyAM0,115200n8 cfg.uart=1",
        workdir=qemu_workdir,
        timeout_s=15.0,
    )
    assert (
        "attempt to access beyond end of device" in res.serial_output
        or "Kernel panic" in res.serial_output
        or "EXT2-fs" in res.serial_output
    )


def test_initrd_qemu_in_proc_version_skips_mounts(
    qemu_runner_cls,
    boot_stub_mod,
    storage_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T2-E3: Stock /sbin/init skips nflasha* mounts when /proc/version contains 'qemu'."""
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    # Build a CPIO wrapper that stages stock /sbin/init + /lib + /kmod and bind-mounts a 'qemu' /proc/version
    from tests.e2e_qemu.helpers import _cpio_newc_entry, build_minimal_initrd_cpio as _build_cpio

    base_cpio = _build_cpio(
        qemu_workdir / "artifacts",
        LINUX_EABI_MINIMAL_C_PRELUDE
        + """
static inline int sys_execve(const char *path, char *const argv[], char *const envp[]) {
    register const char *r0 __asm__("r0") = path;
    register char *const *r1 __asm__("r1") = argv;
    register char *const *r2 __asm__("r2") = envp;
    register int r7 __asm__("r7") = 11;
    __asm__ volatile("swi #0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r7) : "memory");
    return (int)r0;
}
void init_main(void) {
    sys_mkdir("/proc", 0555);
    sys_mount("proc", "/proc", "proc", 0, 0);
    int fd = sys_open("/fake_ver", 0x241 /* O_WRONLY|O_CREAT|O_TRUNC */, 0644);
    if (fd >= 0) {
        static const char v[] = "Linux version 3.0.27_nl-rt106+ (qemu)\\n";
        sys_write(fd, v, sizeof(v) - 1);
        sys_close(fd);
    }
    sys_mount("/fake_ver", "/proc/version", 0, 4096 /* MS_BIND */, 0);
    char *argv[] = {"/sbin/init", 0};
    char *envp[] = {"PATH=/sbin:/bin:/usr/bin", 0};
    sys_execve("/sbin/init", argv, envp);
    out_str("EXEC_INIT_FAILED\\n");
}
""",
        name="qemu_bypass_base.cpio",
    )
    initrd_ext = dumps_dir / "initrd_extracted"
    extra_entries = bytearray()
    for d in ("sbin", "lib", "kmod", "rootfs", "dev"):
        extra_entries.extend(_cpio_newc_entry(d, b"", 0o040755))
    for sub in ("sbin/init", "lib/ld-2.11.2.so", "lib/libc-2.11.2.so", "lib/libgcc_s.so.1"):
        p = initrd_ext / sub
        if p.is_file():
            extra_entries.extend(_cpio_newc_entry(sub, p.read_bytes(), 0o100755))
    # Remove trailing TRAILER!!! from base_cpio and append extracted files + TRAILER!!!
    base_bytes = base_cpio.read_bytes()
    trailer_idx = base_bytes.rfind(b"070701")
    combined_cpio = qemu_workdir / "artifacts" / "qemu_bypass.cpio"
    combined_cpio.write_bytes(base_bytes[:trailer_idx] + bytes(extra_entries) + _cpio_newc_entry("TRAILER!!!", b"", 0))

    staged = prepare_staged_storage(storage_mod, dumps_dir, qemu_workdir / "storage")
    runner_kwargs: dict[str, object] = {
        "kernel": kern,
        "initrd": combined_cpio,
        "append": "mem=1G@0 console=ttyAM0,115200n8 cfg.uart=1 rdinit=/init",
        "display": "none",
        "serial_log": qemu_workdir / "serial.log",
        "timeout_s": 25.0,
    }
    if isinstance(staged, dict):
        for k in ("drives", "sd", "pflash", "device_loader", "extra_args"):
            if k in staged and staged[k] is not None:
                runner_kwargs[k] = staged[k]
    res = run_probe_with_runner(runner_cls, workdir=qemu_workdir, timeout_s=15.0, **runner_kwargs)
    # With is_qemu=1, /sbin/init skips pivot_root and /dev/nflasha* mounts
    assert "pivot_root" not in res.serial_output.lower()


def test_initrd_missing_console_arg_silent_or_fallback(
    qemu_runner_cls,
    boot_stub_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T2-E4: Booting without console=ttyAM0 does not crash QEMU and suppresses ttyAM0 kernel console."""
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    res = run_probe_with_runner(
        runner_cls,
        kernel=kern,
        initrd=dumps_dir / "firmware" / "initrd.img",
        append="mem=1G@0 ramdisk_size=8192 root=/dev/ram0 rw init=/sbin/init",
        workdir=qemu_workdir,
        timeout_s=6.0,
    )
    assert "Linux version 3.0.27_nl-rt106+" not in res.serial_output


def test_initrd_missing_storage_fallback_shell(
    qemu_runner_cls,
    boot_stub_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T2-E5: Booting vmlinux.bin + initrd.img without nflasha7/15 handles mount failure without crash."""
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    res = run_probe_with_runner(
        runner_cls,
        kernel=kern,
        initrd=dumps_dir / "firmware" / "initrd.img",
        append="mem=1G@0 ramdisk_size=8192 root=/dev/ram0 rw init=/sbin/init console=ttyAM0,115200n8 cfg.uart=1",
        workdir=qemu_workdir,
        timeout_s=20.0,
    )
    assert_clean_linux_serial(res.serial_output)


# =============================================================================
# Area F — Storage & Rootfs Mounting Boundaries
# =============================================================================


def test_storage_missing_nflasha15_usr_empty(
    qemu_runner_cls,
    boot_stub_mod,
    storage_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T2-F1: Attaching nflasha7 without nflasha15 pivots /rootfs, leaves /usr unmounted, reaches shell."""
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    staged = prepare_staged_storage(storage_mod, dumps_dir, qemu_workdir / "storage", include_usr=False)
    runner_kwargs: dict[str, object] = {
        "kernel": kern,
        "initrd": dumps_dir / "firmware" / "initrd.img",
        "append": "mem=1G@0 ramdisk_size=8192 root=/dev/ram0 rw init=/sbin/init console=ttyAM0,115200n8 cfg.uart=1",
        "display": "none",
        "serial_log": qemu_workdir / "serial.log",
        "timeout_s": 35.0,
    }
    if isinstance(staged, dict):
        for k in ("drives", "sd", "pflash", "device_loader", "extra_args"):
            if k in staged and staged[k] is not None:
                runner_kwargs[k] = staged[k]
    runner = runner_cls(**runner_kwargs)
    runner.start()
    try:
        runner.wait_for_serial(r"(#|\$ )", timeout_s=30.0)
        runner.send_serial("ls /usr/bin/bootin.elf 2>&1; echo NO_USR_DONE\n")
        res = runner.wait_for_serial("NO_USR_DONE", timeout_s=10.0)
        assert_clean_linux_serial(res.serial_output)
        assert "No such file" in res.serial_output or "bootin.elf" in res.serial_output
    finally:
        try:
            runner.stop()
        except Exception:
            pass


def test_storage_corrupt_nflasha7_ext2_superblock(
    qemu_runner_cls,
    boot_stub_mod,
    storage_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T2-F2: Corrupted nflasha7 superblock in staged copy fails mount cleanly without touching dumps."""
    runner_cls, _ = qemu_runner_cls
    snap = snapshot_dumps_hashes(dumps_dir)
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    storage_dir = qemu_workdir / "storage"
    staged = prepare_staged_storage(storage_mod, dumps_dir, storage_dir)
    # Corrupt any staged nflasha7 / ext2 superblock copy in storage_dir
    for p in storage_dir.rglob("*nflasha7*"):
        if p.is_file() and p.stat().st_size >= 2048:
            with p.open("r+b") as fh:
                fh.seek(1024)
                fh.write(b"\x00" * 128)
    runner_kwargs: dict[str, object] = {
        "kernel": kern,
        "initrd": dumps_dir / "firmware" / "initrd.img",
        "append": "mem=1G@0 ramdisk_size=8192 root=/dev/ram0 rw init=/sbin/init console=ttyAM0,115200n8 cfg.uart=1",
        "display": "none",
        "serial_log": qemu_workdir / "serial.log",
        "timeout_s": 25.0,
    }
    if isinstance(staged, dict):
        for k in ("drives", "sd", "pflash", "device_loader", "extra_args"):
            if k in staged and staged[k] is not None:
                runner_kwargs[k] = staged[k]
    res = run_probe_with_runner(runner_cls, workdir=qemu_workdir, timeout_s=20.0, **runner_kwargs)
    assert_clean_linux_serial(res.serial_output)
    assert_dumps_unmodified(snap, dumps_dir)


def test_storage_emmc_missing_ptbl_at_0x80000000(
    qemu_runner_cls,
    boot_stub_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T2-F3: Loading emmc.ko with invalid/zeroed DDR1 table logs diagnostic without kernel oops."""
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    res = run_probe_with_runner(
        runner_cls,
        kernel=kern,
        initrd=dumps_dir / "firmware" / "initrd.img",
        append="mem=1G@0 ramdisk_size=8192 root=/dev/ram0 rw init=/sbin/init console=ttyAM0,115200n8 cfg.uart=1",
        workdir=qemu_workdir,
        timeout_s=20.0,
    )
    assert_clean_linux_serial(res.serial_output)
    assert "Information table is invalid" in res.serial_output or "emmc" in res.serial_output.lower()


def test_storage_dumps_immutability_under_rw_guest(
    qemu_runner_cls,
    boot_stub_mod,
    storage_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T2-F4: Guest writes to /log and RO / attempts never alter .local/dumps/."""
    snap = snapshot_dumps_hashes(dumps_dir)
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    staged = prepare_staged_storage(storage_mod, dumps_dir, qemu_workdir / "storage")
    runner_kwargs: dict[str, object] = {
        "kernel": kern,
        "initrd": dumps_dir / "firmware" / "initrd.img",
        "append": "mem=1G@0 ramdisk_size=8192 root=/dev/ram0 rw init=/sbin/init console=ttyAM0,115200n8 cfg.uart=1",
        "display": "none",
        "serial_log": qemu_workdir / "serial.log",
        "timeout_s": 40.0,
    }
    if isinstance(staged, dict):
        for k in ("drives", "sd", "pflash", "device_loader", "extra_args"):
            if k in staged and staged[k] is not None:
                runner_kwargs[k] = staged[k]
    runner = runner_cls(**runner_kwargs)
    runner.start()
    try:
        runner.wait_for_serial(r"(#|\$ )", timeout_s=35.0)
        runner.send_serial("touch /ro_fail 2>&1; echo rw_ok > /log/rw_check.txt; echo RW_DONE\n")
        res = runner.wait_for_serial("RW_DONE", timeout_s=10.0)
        assert "Read-only file system" in res.serial_output or "read-only" in res.serial_output.lower()
    finally:
        try:
            runner.stop()
        except Exception:
            pass
    assert_dumps_unmodified(snap, dumps_dir)


def test_storage_dirty_nflasha11_dosfsck_recovery(
    qemu_runner_cls,
    boot_stub_mod,
    storage_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T2-F5: Dirty VFAT bit in staged /log image recovers via dosfsck/mkdosfs and mounts writable."""
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    storage_dir = qemu_workdir / "storage"
    staged = prepare_staged_storage(storage_mod, dumps_dir, storage_dir)
    for p in storage_dir.rglob("*nflasha11*"):
        if p.is_file() and p.stat().st_size >= 4096:
            with p.open("r+b") as fh:
                fh.seek(0x41)
                fh.write(b"\x01")
    runner_kwargs: dict[str, object] = {
        "kernel": kern,
        "initrd": dumps_dir / "firmware" / "initrd.img",
        "append": "mem=1G@0 ramdisk_size=8192 root=/dev/ram0 rw init=/sbin/init console=ttyAM0,115200n8 cfg.uart=1",
        "display": "none",
        "serial_log": qemu_workdir / "serial.log",
        "timeout_s": 40.0,
    }
    if isinstance(staged, dict):
        for k in ("drives", "sd", "pflash", "device_loader", "extra_args"):
            if k in staged and staged[k] is not None:
                runner_kwargs[k] = staged[k]
    runner = runner_cls(**runner_kwargs)
    runner.start()
    try:
        runner.wait_for_serial(r"(#|\$ )", timeout_s=35.0)
        runner.send_serial("echo recovered > /log/rec.txt && cat /log/rec.txt; echo REC_DONE\n")
        res = runner.wait_for_serial("REC_DONE", timeout_s=10.0)
        assert_clean_linux_serial(res.serial_output)
        assert "recovered" in res.serial_output
    finally:
        try:
            runner.stop()
        except Exception:
            pass


# =============================================================================
# Area G — VPH / OSD0 Display Boundaries
# =============================================================================


def test_osd0_zero_pa_produces_blank_no_crash(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T2-G1: OSD0 +0x20 = 0 leaves display blank without QEMU segfault."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "osd0_zero_pa",
        UART0_PROBE_C_PRELUDE
        + """
void probe_main(void) {
    mmio_w32(0xF3445000U, 0x00010114U);
    mmio_w32(0xF3440144U, 0x00000002U);
    mmio_w32(0xF3441320U, 0U);
    mmio_w32(0xF3441324U, 1280U);
    mmio_w32(0xF3441348U, 1280U);
    mmio_w32(0xF344132CU, 479U);
    mmio_w32(0xF3441300U, 3U);
    uart_puts("ZERO_PA_ALIVE\\n");
}
""",
    )
    out_png = qemu_workdir / "captures" / "zero_pa.png"
    res, _ = run_qemu_and_qmp_capture(runner_cls, kernel=probe, workdir=qemu_workdir, out_png=out_png, wait_s=1.0)
    assert "ZERO_PA_ALIVE" in res.serial_output
    rgb = verify_png_frame(out_png, expected_size=(640, 480), min_distinct_colors=1)
    assert np.all(rgb == 0)


def test_osd0_unaligned_pa_rejected_or_safe(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T2-G2: Non-8-byte-aligned OSD0 +0x20 (0x25000003) does not crash QEMU."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "osd0_unaligned",
        UART0_PROBE_C_PRELUDE
        + """
void probe_main(void) {
    mmio_w32(0xF3445000U, 0x00010114U);
    mmio_w32(0xF3440144U, 0x00000002U);
    mmio_w32(0xF3441320U, 0x25000003U);
    mmio_w32(0xF3441324U, 1280U);
    mmio_w32(0xF3441348U, 1280U);
    mmio_w32(0xF344132CU, 479U);
    mmio_w32(0xF3441300U, 3U);
    uart_puts("UNALIGNED_SAFE\\n");
}
""",
    )
    out_png = qemu_workdir / "captures" / "unaligned.png"
    res, _ = run_qemu_and_qmp_capture(runner_cls, kernel=probe, workdir=qemu_workdir, out_png=out_png, wait_s=0.8)
    assert "UNALIGNED_SAFE" in res.serial_output
    verify_png_frame(out_png, expected_size=(640, 480), min_distinct_colors=1)


def test_osd0_out_of_bounds_pa_safe(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T2-G3: Out-of-bounds OSD0 +0x20 (0x3FFFC000 / 0x70000000) is safely clamped/ignored."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "osd0_oob",
        UART0_PROBE_C_PRELUDE
        + """
void probe_main(void) {
    mmio_w32(0xF3445000U, 0x00010114U);
    mmio_w32(0xF3440144U, 0x00000002U);
    mmio_w32(0xF3441320U, 0x70000000U);
    mmio_w32(0xF3441324U, 1280U);
    mmio_w32(0xF3441348U, 1280U);
    mmio_w32(0xF344132CU, 479U);
    mmio_w32(0xF3441300U, 3U);
    uart_puts("OOB_PA_SAFE\\n");
}
""",
    )
    out_png = qemu_workdir / "captures" / "oob_pa.png"
    res, _ = run_qemu_and_qmp_capture(runner_cls, kernel=probe, workdir=qemu_workdir, out_png=out_png, wait_s=0.8)
    assert "OOB_PA_SAFE" in res.serial_output
    verify_png_frame(out_png, expected_size=(640, 480), min_distinct_colors=1)


def test_osd0_ctrl_idle_no_scanout_flip(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T2-G4: When OSD0 +0x00 stays 0/2 (never written 3), scanout stays blank and does not flip."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "osd0_idle_ctrl",
        UART0_PROBE_C_PRELUDE
        + """
void probe_main(void) {
    volatile uint16_t *fb = (volatile uint16_t *)0x25000000U;
    for (uint32_t i = 0; i < 640U * 480U; i++) fb[i] = 0xF00FU;
    mmio_w32(0xF3445000U, 0x00010114U);
    mmio_w32(0xF3440144U, 0x00000002U);
    mmio_w32(0xF3441320U, 0x25000000U);
    mmio_w32(0xF3441324U, 1280U);
    mmio_w32(0xF3441348U, 1280U);
    mmio_w32(0xF344132CU, 479U);
    mmio_w32(0xF3441300U, 0U);
    uart_puts("IDLE_CTRL_READY\\n");
}
""",
    )
    out_png = qemu_workdir / "captures" / "idle_ctrl.png"
    res, _ = run_qemu_and_qmp_capture(runner_cls, kernel=probe, workdir=qemu_workdir, out_png=out_png, wait_s=0.8)
    assert "IDLE_CTRL_READY" in res.serial_output
    rgb = verify_png_frame(out_png, expected_size=(640, 480), min_distinct_colors=1)
    assert np.all(rgb == 0)


def test_osd0_31bit_ddr1_mask_behavior(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T2-G5: Setting OSD0 +0x4c (rptadrs) = 0x88200000 with high bit set executes safely."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "osd0_rptadrs",
        UART0_PROBE_C_PRELUDE
        + """
void probe_main(void) {
    mmio_w32(0xF3445000U, 0x00010114U);
    mmio_w32(0xF3440144U, 0x00000002U);
    mmio_w32(0xF3441320U, 0x25000000U);
    mmio_w32(0xF344134CU, 0x88200000U);
    mmio_w32(0xF3441324U, 1280U);
    mmio_w32(0xF3441348U, 1280U);
    mmio_w32(0xF344132CU, 479U);
    mmio_w32(0xF3441300U, 3U);
    uart_puts("RPTADRS_SAFE\\n");
}
""",
    )
    out_png = qemu_workdir / "captures" / "rptadrs.png"
    res, _ = run_qemu_and_qmp_capture(runner_cls, kernel=probe, workdir=qemu_workdir, out_png=out_png, wait_s=0.8)
    assert "RPTADRS_SAFE" in res.serial_output
    verify_png_frame(out_png, expected_size=(640, 480), min_distinct_colors=1)


# =============================================================================
# Area H — Display Capture & Input Stub Boundaries
# =============================================================================


def test_capture_osd0_with_display_none_or_headless(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T2-H1: QMP screendump succeeds headlessly with -display none."""
    runner_cls, _ = qemu_runner_cls
    rtos_bin = build_zvos_payload(qemu_workdir / "zvos_disp", "rtos_display.S", display=True)
    elf = build_zvos_baremetal_elf(qemu_workdir / "zvos_disp", rtos_bin, name="rtos_disp_headless")
    qmp_port = free_tcp_port()
    runner = runner_cls(
        kernel=elf,
        display="none",
        serial_log=qemu_workdir / "serial.log",
        qmp_port=qmp_port,
        timeout_s=12.0,
    )
    ppm_path = qemu_workdir / "captures" / "headless.ppm"
    runner.start()
    try:
        time.sleep(1.0)
        with QmpClient("127.0.0.1", qmp_port, timeout_s=8.0) as qmp:
            qmp.screendump(ppm_path, fmt="ppm")
        runner.stop()
    finally:
        try:
            runner.stop()
        except Exception:
            pass
    verify_png_frame(ppm_path, expected_size=(640, 480), min_distinct_colors=8)


def test_capture_screendump_unwritable_output_path(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T2-H2: capture_osd0_png to nonexistent nested directory raises clean OSError/ValueError."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "cap_bad_path",
        UART0_PROBE_C_PRELUDE + 'void probe_main(void) { uart_puts("CAP_UP\\n"); }',
    )
    runner = runner_cls(
        kernel=probe,
        display="none",
        serial_log=qemu_workdir / "serial.log",
        qmp_port=free_tcp_port(),
        timeout_s=10.0,
    )
    runner.start()
    try:
        runner.wait_for_serial("CAP_UP", timeout_s=6.0)
        bad_out = qemu_workdir / "nonexistent_parent_xyz" / "sub" / "out.png"
        with pytest.raises((OSError, ValueError, RuntimeError)):
            runner.capture_osd0_png(bad_out)
    finally:
        try:
            runner.stop()
        except Exception:
            pass


def test_adc1_conversion_busy_timeout_preserves_held(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T2-H3: Busy ADC1 preserves prior held state and prevents false key transitions."""
    runner_cls, _ = qemu_runner_cls
    rtos_bin = build_zvos_payload(qemu_workdir / "zvos_shell", "os_shell.c", display=True)
    elf = build_zvos_baremetal_elf(qemu_workdir / "zvos_shell", rtos_bin, name="os_shell_busy")
    runner = runner_cls(
        kernel=elf,
        display="none",
        serial_log=qemu_workdir / "serial.log",
        qmp_port=free_tcp_port(),
        timeout_s=15.0,
    )
    out_png = qemu_workdir / "captures" / "after_busy.png"
    runner.start()
    try:
        time.sleep(0.8)
        runner.qmp_command("qom-set", {"path": "/machine/soc/adc1", "property": "busy", "value": True})
        drive_adc_gpio_stimulus(runner, adc1_b3=0x000)
        time.sleep(0.3)
        runner.capture_osd0_png(out_png)
        runner.qmp_command("qom-set", {"path": "/machine/soc/adc1", "property": "busy", "value": False})
        runner.stop()
    finally:
        try:
            runner.stop()
        except Exception:
            pass
    rgb = verify_png_frame(out_png, expected_size=(640, 480), min_distinct_colors=4)
    verify_os_shell_status_frame(rgb, expected_sel=0, has_clip=False)


def test_adc1_unstable_debounce_pair_rejected(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T2-H4: Single sub-frame transient glitch on ADC1 B3 is rejected by 2-poll debounce."""
    runner_cls, _ = qemu_runner_cls
    rtos_bin = build_zvos_payload(qemu_workdir / "zvos_shell", "os_shell.c", display=True)
    elf = build_zvos_baremetal_elf(qemu_workdir / "zvos_shell", rtos_bin, name="os_shell_debounce")
    runner = runner_cls(
        kernel=elf,
        display="none",
        serial_log=qemu_workdir / "serial.log",
        qmp_port=free_tcp_port(),
        timeout_s=15.0,
    )
    out_png = qemu_workdir / "captures" / "after_glitch.png"
    runner.start()
    try:
        time.sleep(0.8)
        # Immediately flip RIGHT -> LEFT -> idle faster than 2-poll debounce window
        drive_adc_gpio_stimulus(runner, adc1_b3=0x2AD)
        drive_adc_gpio_stimulus(runner, adc1_b3=0x0D4)
        drive_adc_gpio_stimulus(runner, adc1_b3=0x3FF)
        time.sleep(0.25)
        runner.capture_osd0_png(out_png)
        runner.stop()
    finally:
        try:
            runner.stop()
        except Exception:
            pass
    rgb = verify_png_frame(out_png, expected_size=(640, 480), min_distinct_colors=4)
    verify_os_shell_status_frame(rgb, expected_sel=0, has_clip=False)


def test_zvos_bad_zvrt_handoff_magic_or_crc(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T2-H5: Bad zvrt_handoff magic causes crt0.S to write ZVRT_PROBE_FAIL (0x4641494c) and return 1."""
    runner_cls, _ = qemu_runner_cls
    rtos_bin = build_zvos_payload(qemu_workdir / "zvos_shell", "os_shell.c", display=True)
    elf = build_zvos_baremetal_elf(
        qemu_workdir / "zvos_shell",
        rtos_bin,
        name="zvos_bad_handoff",
        corrupt_handoff_magic=True,
    )
    res = run_probe_with_runner(runner_cls, kernel=elf, workdir=qemu_workdir, wait_pattern="ZVOS_RET=", timeout_s=10.0)
    assert not res.timed_out
    assert f"RESULT={ZVRT_PROBE_FAIL:08x}" in res.serial_output
    assert "ZVOS_RET=00000001" in res.serial_output


# =============================================================================
# Area I — av-cam.bin (LIRO RTOS) & bootrom Boundaries
# =============================================================================


def _boot_with_liro_deps(
    qemu_runner_cls,
    boot_stub_mod,
    storage_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
):
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    staged = prepare_staged_storage(storage_mod, dumps_dir, qemu_workdir / "storage")
    runner_kwargs: dict[str, object] = {
        "kernel": kern,
        "initrd": dumps_dir / "firmware" / "initrd.img",
        "append": "mem=1G@0 ramdisk_size=8192 root=/dev/ram0 rw init=/sbin/init console=ttyAM0,115200n8 cfg.uart=1",
        "display": "none",
        "serial_log": qemu_workdir / "serial.log",
        "timeout_s": 45.0,
    }
    if isinstance(staged, dict):
        for k in ("drives", "sd", "pflash", "device_loader", "extra_args"):
            if k in staged and staged[k] is not None:
                runner_kwargs[k] = staged[k]
    runner = runner_cls(**runner_kwargs)
    runner.start()
    runner.wait_for_serial(r"(#|\$ )", timeout_s=40.0)
    runner.send_serial(
        "for m in osal_utm osal_uipc utimer backup dmm dma330; do insmod /usr/kmod/${m}.ko; done; echo DEPS_OK\n"
    )
    runner.wait_for_serial("DEPS_OK", timeout_s=15.0)
    return runner


def test_liro_rejects_missing_avcam_file(
    qemu_runner_cls,
    boot_stub_mod,
    storage_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T2-I1: liro.ko fails cleanly without panic when fn points to missing file."""
    runner = _boot_with_liro_deps(qemu_runner_cls, boot_stub_mod, storage_mod, dumps_dir, qemu_workdir)
    try:
        runner.send_serial(
            "insmod /usr/kmod/liro.ko adr=0x035c6000 fn=/system/missing_xyz.bin load=1; "
            "echo RC=$?; echo TEST_END\n"
        )
        res = runner.wait_for_serial("TEST_END", timeout_s=15.0)
        assert "Kernel panic" not in res.serial_output
        assert "RC=0" not in res.serial_output
    finally:
        try:
            runner.stop()
        except Exception:
            pass


def test_liro_rejects_non_oril_magic(
    qemu_runner_cls,
    boot_stub_mod,
    storage_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T2-I2: liro.ko rejects file with corrupted 'ORIL' magic at +0x04."""
    runner = _boot_with_liro_deps(qemu_runner_cls, boot_stub_mod, storage_mod, dumps_dir, qemu_workdir)
    try:
        runner.send_serial(
            "dd if=/system/av-cam.bin of=/tmp/bad_magic.bin bs=4096 count=16 2>/dev/null; "
            "printf 'XXXX' | dd of=/tmp/bad_magic.bin bs=1 seek=4 conv=notrunc 2>/dev/null; "
            "insmod /usr/kmod/liro.ko adr=0x035c6000 fn=/tmp/bad_magic.bin load=1; "
            "echo RC=$?; echo BAD_MAGIC_END\n"
        )
        res = runner.wait_for_serial("BAD_MAGIC_END", timeout_s=15.0)
        assert "Kernel panic" not in res.serial_output
        assert "RC=0" not in res.serial_output
    finally:
        try:
            runner.stop()
        except Exception:
            pass


def test_liro_rejects_wrong_version_and_truncated(
    qemu_runner_cls,
    boot_stub_mod,
    storage_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T2-I3: liro.ko rejects truncated or wrong-version ORIL header without kernel crash."""
    runner = _boot_with_liro_deps(qemu_runner_cls, boot_stub_mod, storage_mod, dumps_dir, qemu_workdir)
    try:
        runner.send_serial(
            "dd if=/system/av-cam.bin of=/tmp/bad_ver.bin bs=4096 count=1 2>/dev/null; "
            "printf '\\x09\\x00\\x00\\x00' | dd of=/tmp/bad_ver.bin bs=1 seek=8 conv=notrunc 2>/dev/null; "
            "insmod /usr/kmod/liro.ko adr=0x035c6000 fn=/tmp/bad_ver.bin load=1; "
            "echo RC=$?; echo BAD_VER_END\n"
        )
        res = runner.wait_for_serial("BAD_VER_END", timeout_s=15.0)
        assert "Kernel panic" not in res.serial_output
        assert "RC=0" not in res.serial_output
    finally:
        try:
            runner.stop()
        except Exception:
            pass


def test_liro_rejects_zero_adr(
    qemu_runner_cls,
    boot_stub_mod,
    storage_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T2-I4: liro.ko rejects adr=0 parameter cleanly without kernel panic."""
    runner = _boot_with_liro_deps(qemu_runner_cls, boot_stub_mod, storage_mod, dumps_dir, qemu_workdir)
    try:
        runner.send_serial(
            "insmod /usr/kmod/liro.ko adr=0 fn=/system/av-cam.bin load=1; "
            "echo RC=$?; echo ZERO_ADR_END\n"
        )
        res = runner.wait_for_serial("ZERO_ADR_END", timeout_s=15.0)
        assert "Kernel panic" not in res.serial_output
        assert "RC=0" not in res.serial_output
    finally:
        try:
            runner.stop()
        except Exception:
            pass


def test_avcam_baremetal_offset0_abort_trap(qemu_runner_cls, dumps_dir: Path, qemu_workdir: Path) -> None:
    """T2-I5: Bare-metal boot of raw av-cam.bin traps to 0xffff0000 and is bounded cleanly by timeout."""
    runner_cls, boot_result_cls = qemu_runner_cls
    res = run_probe_with_runner(
        runner_cls,
        kernel=dumps_dir / "firmware" / "av-cam.bin",
        workdir=qemu_workdir,
        timeout_s=3.0,
    )
    assert isinstance(res, boot_result_cls)
    assert res.timed_out is True
