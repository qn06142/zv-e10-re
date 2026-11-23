"""Tier 1: Isolated Happy-Path E2E Feature Tests.

Stock storage (former T1-F) and LIRO execution (former T1-I2..I5)
are consolidated in test_stock_milestones.py using verified boot contracts."""
from __future__ import annotations

import re
import struct
import subprocess
import time
from pathlib import Path

import numpy as np
import pytest

from tests.e2e_qemu.helpers import (
    LINUX_EABI_MINIMAL_C_PRELUDE,
    QEMU_TARBALL_SHA256,
    UART0_PROBE_C_PRELUDE,
    ZVRT_PROBE_OK,
    QmpClient,
    assert_clean_linux_serial,
    assert_dumps_unmodified,
    assert_r3_zve10_qemu_unmodified,
    build_baremetal_arm_probe,
    build_minimal_initrd_cpio,
    build_zvos_baremetal_elf,
    build_zvos_payload,
    drive_adc_gpio_stimulus,
    file_sha256,
    free_tcp_port,
    prepare_staged_storage,
    prepare_stock_kernel_with_boot_stub,
    rgba4444_bytes_to_rgb_array,
    run_probe_with_runner,
    run_qemu_and_qmp_capture,
    run_subprocess_deadline,
    snapshot_dumps_hashes,
    ucrt64_env,
    verify_os_shell_status_frame,
    verify_png_frame,
    verify_rtos_display_frame,
)

pytestmark = [pytest.mark.e2e_qemu, pytest.mark.tier1]


# =============================================================================
# Area A — Feature #1: QEMU 11.1.2 Build & Packaging
# =============================================================================


def test_qemu_binary_exists_and_version(qemu_bin_path: Path) -> None:
    """T1-A1: Built qemu-system-arm.exe executes --version and reports QEMU 11.1.2."""
    res = run_subprocess_deadline(
        [str(qemu_bin_path), "--version"],
        env=ucrt64_env(),
        timeout_s=10.0,
    )
    assert res.returncode == 0, f"qemu-system-arm.exe --version failed: {res.stderr}"
    assert re.search(r"QEMU emulator version 11\.1\.2", res.stdout), (
        f"Unexpected QEMU version output: {res.stdout!r}"
    )


def test_zve10_machine_registered(qemu_bin_path: Path) -> None:
    """T1-A2: qemu-system-arm.exe -M help includes the zve10 Sony ZV-E10 machine."""
    res = run_subprocess_deadline(
        [str(qemu_bin_path), "-M", "help"],
        env=ucrt64_env(),
        timeout_s=10.0,
    )
    assert res.returncode == 0, f"-M help failed: {res.stderr}"
    zve10_lines = [ln for ln in res.stdout.splitlines() if re.match(r"^\s*zve10\b", ln)]
    assert zve10_lines, f"Machine 'zve10' not registered in -M help:\n{res.stdout}"
    assert "Sony ZV-E10" in zve10_lines[0], f"Unexpected zve10 line: {zve10_lines[0]!r}"


def test_cortex_a9_cpu_supported(qemu_bin_path: Path) -> None:
    """T1-A3: qemu-system-arm.exe -cpu help includes cortex-a9."""
    res = run_subprocess_deadline(
        [str(qemu_bin_path), "-cpu", "help"],
        env=ucrt64_env(),
        timeout_s=10.0,
    )
    assert res.returncode == 0, f"-cpu help failed: {res.stderr}"
    assert re.search(r"\bcortex-a9\b", res.stdout), (
        f"CPU 'cortex-a9' missing from -cpu help:\n{res.stdout}"
    )


def test_build_qemu_tarball_sha256_verify(build_qemu_mod, repo_root: Path) -> None:
    """T1-A4: emulator.build_qemu tarball verification matches expected QEMU 11.1.2 SHA-256."""
    tarball = repo_root / ".local" / "emulator" / "qemu-11.1.2.tar.xz"
    assert tarball.is_file(), f"Staged QEMU tarball missing: {tarball}"
    actual_sha = file_sha256(tarball)
    assert actual_sha == QEMU_TARBALL_SHA256, (
        f"Tarball SHA-256 mismatch: {actual_sha} != {QEMU_TARBALL_SHA256}"
    )
    verify_fn = getattr(build_qemu_mod, "verify_tarball", None) or getattr(
        build_qemu_mod, "verify_tarball_sha256", None
    )
    if callable(verify_fn):
        verify_fn(tarball)


def test_zve10_qmp_query_machines(qemu_bin_path: Path, qemu_workdir: Path) -> None:
    """T1-A5: Live QEMU -M zve10 -S answers QMP query-machines and query-version cleanly."""
    qmp_port = free_tcp_port()
    cmd = [
        str(qemu_bin_path),
        "-M",
        "zve10",
        "-cpu",
        "cortex-a9",
        "-smp",
        "4",
        "-m",
        "1024",
        "-S",
        "-display",
        "none",
        "-serial",
        "none",
        "-qmp",
        f"tcp:127.0.0.1:{qmp_port},server=on,wait=off",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=ucrt64_env(),
        cwd=str(qemu_workdir),
    )
    try:
        with QmpClient("127.0.0.1", qmp_port, timeout_s=10.0) as qmp:
            ver = qmp.query_version()
            assert (ver["qemu"]["major"], ver["qemu"]["minor"], ver["qemu"]["micro"]) == (11, 1, 2)
            machines = {m["name"]: m for m in qmp.query_machines()}
            assert "zve10" in machines, f"zve10 missing from QMP query-machines: {list(machines)}"
            assert machines["zve10"].get("cpu-max", 0) >= 4, machines["zve10"]
            qmp.quit()
        rc = proc.wait(timeout=10)
        assert rc == 0, f"QEMU exited with code {rc}"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


# =============================================================================
# Area B — Feature #2: Base ZV-E10 SoC & Peripherals
# =============================================================================


def test_soc_uart0_pl011_tx(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T1-B1: Bare-metal probe writing to PL011 UART0 (0xf2000000) emits captured serial text."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "uart0_tx",
        UART0_PROBE_C_PRELUDE
        + """
void probe_main(void) {
    uart_puts("UART0_OK\\n");
}
""",
    )
    res = run_probe_with_runner(runner_cls, kernel=probe, workdir=qemu_workdir, wait_pattern="UART0_OK", timeout_s=8.0)
    assert not res.timed_out
    assert "UART0_OK" in res.serial_output


def test_soc_ddr0_ddr1_esram_rw(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T1-B2: Bare-metal probe verifies R/W integrity across DDR0, DDR1 (0x80000000), and eSRAM."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "mem_map",
        UART0_PROBE_C_PRELUDE
        + """
void probe_main(void) {
    mmio_w32(0x00100000U, 0xCAFEBABEU);
    if (mmio_r32(0x00100000U) == 0xCAFEBABEU) uart_puts("DDR0_OK\\n");
    mmio_w32(0x80000000U, 0x5A1234A5U);
    if (mmio_r32(0x80000000U) == 0x5A1234A5U) uart_puts("DDR1_OK\\n");
    mmio_w32(0xFE005000U, 0xDEADBEEFU);
    if (mmio_r32(0xFE005000U) == 0xDEADBEEFU) uart_puts("ESRAM_OK\\n");
    uart_puts("MEM_DONE\\n");
}
""",
    )
    res = run_probe_with_runner(runner_cls, kernel=probe, workdir=qemu_workdir, wait_pattern="MEM_DONE", timeout_s=8.0)
    assert not res.timed_out
    assert "DDR0_OK" in res.serial_output
    assert "DDR1_OK" in res.serial_output
    assert "ESRAM_OK" in res.serial_output


def test_soc_sony_hwtimer_tick_and_irq(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T1-B3: sony-hwtimer #0 advances counter and delivers GIC SPI IRQ 153."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "hwtimer_irq",
        UART0_PROBE_C_PRELUDE
        + """
static volatile uint32_t irq153_seen = 0;
void probe_irq_handler(void) {
    uint32_t iar = mmio_r32(0xF800010CU);
    uint32_t irq = iar & 0x3FFU;
    if (irq == 153U) {
        irq153_seen = 1U;
        mmio_w32(0xF2403004U, 1U);
    }
    mmio_w32(0xF8000110U, iar);
}
void probe_main(void) {
    mmio_w32(0xF8001000U, 1U);
    mmio_w32(0xF8000104U, 0xFFU);
    mmio_w32(0xF8000100U, 1U);
    mmio_w32(0xF8001100U + (153U / 32U) * 4U, 1U << (153U % 32U));
    mmio_w32(0xF2403000U, 0x80000000U);
    mmio_w32(0xF2403008U, 4000U);
    mmio_w32(0xF2403000U, 0x00001100U);
    uint32_t c0 = mmio_r32(0xF240300CU);
    __asm__ volatile("cpsie i");
    for (volatile uint32_t i = 0; i < 2000000U && !irq153_seen; i++) {}
    uint32_t c1 = mmio_r32(0xF240300CU);
    if (c1 != c0) uart_puts("TIMER_CNT_OK\\n");
    if (irq153_seen) uart_puts("TIMER_IRQ153_OK\\n");
    uart_puts("TIMER_DONE\\n");
}
""",
        with_irq_vector=True,
    )
    res = run_probe_with_runner(runner_cls, kernel=probe, workdir=qemu_workdir, wait_pattern="TIMER_DONE", timeout_s=8.0)
    assert not res.timed_out
    assert "TIMER_CNT_OK" in res.serial_output
    assert "TIMER_IRQ153_OK" in res.serial_output


def test_soc_sugilite_and_gpe_mmio(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T1-B4: Sugilite (0xf3400080) returns 0x15 and GPE fence packet raises GIC IRQ 76."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "sugi_gpe",
        UART0_PROBE_C_PRELUDE
        + """
static volatile uint32_t irq76_seen = 0;
static uint32_t gpe_pkt[8] __attribute__((aligned(16))) = {
    0x0116F000U, 0x02100000U, 0x0117F000U, 1U,
    0x0044F000U, 0U, 0x0010F000U, 0x12345678U
};
void probe_irq_handler(void) {
    uint32_t iar = mmio_r32(0xF800010CU);
    if ((iar & 0x3FFU) == 76U) {
        irq76_seen = 1U;
        mmio_w32(0xF1001000U, 0U);
    }
    mmio_w32(0xF8000110U, iar);
}
void probe_main(void) {
    if (mmio_r32(0xF3400080U) == 0x15U) uart_puts("SUGI_15_OK\\n");
    mmio_w32(0xF8001000U, 1U);
    mmio_w32(0xF8000104U, 0xFFU);
    mmio_w32(0xF8000100U, 1U);
    mmio_w32(0xF8001100U + (76U / 32U) * 4U, 1U << (76U % 32U));
    __asm__ volatile("cpsie i");
    mmio_w32(0xF1001804U, (uint32_t)(uintptr_t)gpe_pkt);
    mmio_w32(0xF1001800U, 4U);
    for (volatile uint32_t i = 0; i < 500000U && !irq76_seen; i++) {}
    if (irq76_seen && mmio_r32(0xF1001080U) == 0x12345678U) uart_puts("GPE_IRQ76_OK\\n");
    uart_puts("SG_DONE\\n");
}
""",
        with_irq_vector=True,
    )
    res = run_probe_with_runner(runner_cls, kernel=probe, workdir=qemu_workdir, wait_pattern="SG_DONE", timeout_s=8.0)
    assert not res.timed_out
    assert "SUGI_15_OK" in res.serial_output
    assert "GPE_IRQ76_OK" in res.serial_output


def test_soc_unimp_mmio_no_abort(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T1-B5: Unimplemented SoC MMIO reads/writes do not raise ARM Data Abort."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "unimp_mmio",
        UART0_PROBE_C_PRELUDE
        + """
void probe_main(void) {
    mmio_w32(0xF2990000U, 0x12345678U);
    (void)mmio_r32(0xF2990004U);
    uart_puts("UNIMP_OK\\n");
}
""",
    )
    res = run_probe_with_runner(runner_cls, kernel=probe, workdir=qemu_workdir, wait_pattern="UNIMP_OK", timeout_s=8.0)
    assert not res.timed_out
    assert "UNIMP_OK" in res.serial_output


# =============================================================================
# Area C — Feature #3: Stock vmlinux.bin Boot & ATAGs Preservation
# =============================================================================


def test_stock_vmlinux_reaches_banner(
    qemu_runner_cls,
    boot_stub_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T1-C1: Stock vmlinux.bin via boot_stub boots and emits Linux 3.0.27_nl-rt106+ banner."""
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    initrd = build_minimal_initrd_cpio(
        qemu_workdir / "artifacts",
        LINUX_EABI_MINIMAL_C_PRELUDE + 'void init_main(void) { out_str("BANNER_INIT_OK\\n"); }',
    )
    res = run_probe_with_runner(
        runner_cls,
        kernel=kern,
        initrd=initrd,
        append="mem=1G@0 console=ttyAM0,115200n8 cfg.uart=1 rdinit=/init",
        workdir=qemu_workdir,
        wait_pattern="BANNER_INIT_OK",
        timeout_s=20.0,
    )
    assert not res.timed_out
    assert_clean_linux_serial(res.serial_output)
    assert "Linux version 3.0.27_nl-rt106+" in res.serial_output


def test_stock_vmlinux_atags_cmdline_preserved(
    qemu_runner_cls,
    boot_stub_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T1-C2: ATAGs r2 survives ej_head_init (0x17024) and delivers custom cmdline to /proc/cmdline."""
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    initrd = build_minimal_initrd_cpio(
        qemu_workdir / "artifacts",
        LINUX_EABI_MINIMAL_C_PRELUDE
        + """
void init_main(void) {
    sys_mkdir("/proc", 0555);
    sys_mount("proc", "/proc", "proc", 0, 0);
    out_str("CMDLINE_BEGIN\\n");
    dump_proc_file("/proc/cmdline");
    out_str("\\nCMDLINE_END\\n");
}
""",
    )
    res = run_probe_with_runner(
        runner_cls,
        kernel=kern,
        initrd=initrd,
        append="mem=1G@0 console=ttyAM0,115200n8 cfg.uart=1 pmca_e2e_tag=atag_ok rdinit=/init",
        workdir=qemu_workdir,
        wait_pattern="CMDLINE_END",
        timeout_s=20.0,
    )
    assert not res.timed_out
    assert_clean_linux_serial(res.serial_output)
    assert "pmca_e2e_tag=atag_ok" in res.serial_output


def test_stock_vmlinux_mach_type_3497(
    qemu_runner_cls,
    boot_stub_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T1-C3: Machine ID 3497 is accepted by stock vmlinux.bin without unrecognized machine error."""
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    initrd = build_minimal_initrd_cpio(
        qemu_workdir / "artifacts",
        LINUX_EABI_MINIMAL_C_PRELUDE + 'void init_main(void) { out_str("MACH_3497_OK\\n"); }',
    )
    res = run_probe_with_runner(
        runner_cls,
        kernel=kern,
        initrd=initrd,
        append="mem=1G@0 console=ttyAM0,115200n8 cfg.uart=1 rdinit=/init",
        workdir=qemu_workdir,
        wait_pattern="MACH_3497_OK",
        timeout_s=20.0,
    )
    assert not res.timed_out
    assert "unrecognized" not in res.serial_output.lower()
    assert "unsupported machine" not in res.serial_output.lower()
    assert "MACH_3497_OK" in res.serial_output


def test_stock_vmlinux_smp_secondary_hold(
    qemu_runner_cls,
    boot_stub_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T1-C4: Stock vmlinux.bin with -smp 2 activates secondary CPU via eSRAM hold pen."""
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    initrd = build_minimal_initrd_cpio(
        qemu_workdir / "artifacts",
        LINUX_EABI_MINIMAL_C_PRELUDE
        + """
void init_main(void) {
    sys_mkdir("/proc", 0555);
    sys_mount("proc", "/proc", "proc", 0, 0);
    out_str("CPUINFO_BEGIN\\n");
    dump_proc_file("/proc/cpuinfo");
    out_str("CPUINFO_END\\n");
}
""",
    )
    res = run_probe_with_runner(
        runner_cls,
        kernel=kern,
        initrd=initrd,
        smp=2,
        append="mem=1G@0 console=ttyAM0,115200n8 cfg.uart=1 rdinit=/init",
        workdir=qemu_workdir,
        wait_pattern="CPUINFO_END",
        timeout_s=25.0,
    )
    assert not res.timed_out
    assert_clean_linux_serial(res.serial_output)
    assert "processor\t: 1" in res.serial_output or "CPU1: Booted secondary processor" in res.serial_output


def test_stock_vmlinux_ddr0_1g_memory_map(
    qemu_runner_cls,
    boot_stub_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T1-C5: Stock vmlinux.bin with mem=1G@0 exposes ~1 GiB MemTotal in /proc/meminfo."""
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    initrd = build_minimal_initrd_cpio(
        qemu_workdir / "artifacts",
        LINUX_EABI_MINIMAL_C_PRELUDE
        + """
void init_main(void) {
    sys_mkdir("/proc", 0555);
    sys_mount("proc", "/proc", "proc", 0, 0);
    out_str("MEMINFO_BEGIN\\n");
    dump_proc_file("/proc/meminfo");
    out_str("MEMINFO_END\\n");
}
""",
    )
    res = run_probe_with_runner(
        runner_cls,
        kernel=kern,
        initrd=initrd,
        append="mem=1G@0 console=ttyAM0,115200n8 cfg.uart=1 rdinit=/init",
        workdir=qemu_workdir,
        wait_pattern="MEMINFO_END",
        timeout_s=20.0,
    )
    assert not res.timed_out
    m = re.search(r"MemTotal:\s+(\d+)\s+kB", res.serial_output)
    assert m is not None, f"MemTotal missing in serial output:\n{res.serial_output}"
    assert int(m.group(1)) > 950_000, f"Expected ~1 GiB MemTotal, got {m.group(1)} kB"


# =============================================================================
# Area D — Feature #4 + R3: Automated QemuRunner & Integrity Guards
# =============================================================================


def test_runner_start_wait_stop(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T1-D1: QemuRunner start/wait_for_serial/stop returns populated BootResult cleanly."""
    runner_cls, boot_result_cls = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "runner_smoke",
        UART0_PROBE_C_PRELUDE + 'void probe_main(void) { uart_puts("RUNNER_READY_TOKEN\\n"); }',
    )
    runner = runner_cls(kernel=probe, display="none", serial_log=qemu_workdir / "serial.log", timeout_s=10.0)
    runner.start()
    try:
        wait_res = runner.wait_for_serial("RUNNER_READY_TOKEN", timeout_s=10.0)
        stop_res = runner.stop()
    finally:
        try:
            runner.stop()
        except Exception:
            pass
    final = stop_res if isinstance(stop_res, boot_result_cls) else wait_res
    assert isinstance(final, boot_result_cls)
    assert final.timed_out is False
    assert final.elapsed_s < 10.0
    assert "RUNNER_READY_TOKEN" in final.serial_output


def test_runner_serial_log_file_persistence(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T1-D2: QemuRunner persists captured UART0 bytes to serial_log on disk."""
    runner_cls, _ = qemu_runner_cls
    log_file = qemu_workdir / "uart0_persisted.log"
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "serial_persist",
        UART0_PROBE_C_PRELUDE + 'void probe_main(void) { uart_puts("PERSIST_BYTES_1234\\n"); }',
    )
    runner = runner_cls(kernel=probe, display="none", serial_log=log_file, timeout_s=10.0)
    runner.start()
    try:
        runner.wait_for_serial("PERSIST_BYTES_1234", timeout_s=8.0)
        runner.stop()
    finally:
        try:
            runner.stop()
        except Exception:
            pass
    assert log_file.is_file(), f"serial_log file not created: {log_file}"
    content = log_file.read_text(encoding="latin1", errors="replace")
    assert "PERSIST_BYTES_1234" in content


def test_runner_qmp_status_and_quit(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T1-D3: QemuRunner qmp_command('query-status') succeeds and stop() shuts down QEMU."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "qmp_idle",
        UART0_PROBE_C_PRELUDE + 'void probe_main(void) { uart_puts("QMP_PROBE_UP\\n"); }',
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
        runner.wait_for_serial("QMP_PROBE_UP", timeout_s=8.0)
        status = runner.qmp_command("query-status")
        assert isinstance(status, dict) and "running" in status, f"Unexpected query-status: {status}"
        res = runner.stop()
        assert res.timed_out is False
    finally:
        try:
            runner.stop()
        except Exception:
            pass


@pytest.mark.r3_guard
def test_r3_zve10_qemu_unmodified(zve10_qemu_dir: Path) -> None:
    """T1-D4: R3 read-only reference repo D:\\02_Development_And_Projects\\zve10-qemu matches baseline."""
    snap = assert_r3_zve10_qemu_unmodified(zve10_qemu_dir)
    assert snap["head"] == "42554a639e005455a1cc492744bd77341e7c41d2"


@pytest.mark.r3_guard
def test_dumps_dir_readonly_hashes_unchanged(dumps_dir: Path) -> None:
    """T1-D5: Read-only .local/dumps/ firmware and flash image SHA-256 digests remain intact."""
    snap = snapshot_dumps_hashes(dumps_dir)
    assert len(snap) == 6
    assert_dumps_unmodified(snap, dumps_dir)


# =============================================================================
# Area E — Feature #5: Stock Kernel + initrd.img Userspace Boot
# =============================================================================


def test_stock_initrd_ext2_boot_to_init(
    qemu_runner_cls,
    boot_stub_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T1-E1: Unmodified vmlinux.bin + initrd.img mounts ext2 ramdisk and starts /sbin/init."""
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
        wait_pattern=r"(#|\$ |ash|login|init)",
        timeout_s=30.0,
    )
    assert not res.timed_out, f"Timed out waiting for init/shell:\n{res.serial_output[-1500:]}"
    assert_clean_linux_serial(res.serial_output)
    assert "RAMDISK: ext2" in res.serial_output or "Mounted root (ext2 filesystem)" in res.serial_output


def test_stock_initrd_proc_version_no_qemu(
    qemu_runner_cls,
    boot_stub_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T1-E2: Guest /proc/version matches stock kernel and omits 'qemu' (preventing /sbin/init bypass)."""
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    runner = runner_cls(
        kernel=kern,
        initrd=dumps_dir / "firmware" / "initrd.img",
        append="mem=1G@0 ramdisk_size=8192 root=/dev/ram0 rw init=/sbin/init console=ttyAM0,115200n8 cfg.uart=1",
        display="none",
        serial_log=qemu_workdir / "serial.log",
        timeout_s=35.0,
    )
    runner.start()
    try:
        runner.wait_for_serial(r"(#|\$ )", timeout_s=30.0)
        runner.send_serial("cat /proc/version\n")
        res = runner.wait_for_serial("3.0.27_nl-rt106+", timeout_s=10.0)
        assert_clean_linux_serial(res.serial_output)
        ver_lines = [ln for ln in res.serial_output.splitlines() if "3.0.27_nl-rt106+" in ln]
        assert ver_lines, f"/proc/version line missing:\n{res.serial_output}"
        assert "qemu" not in ver_lines[-1].lower(), (
            f"/proc/version must not contain 'qemu': {ver_lines[-1]!r}"
        )
    finally:
        try:
            runner.stop()
        except Exception:
            pass


def test_stock_initrd_drivers1_insmod(
    qemu_runner_cls,
    boot_stub_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T1-E3: /sbin/init loads drivers1 kernel modules (devno, dmac, ldec, emmc) cleanly."""
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    runner = runner_cls(
        kernel=kern,
        initrd=dumps_dir / "firmware" / "initrd.img",
        append="mem=1G@0 ramdisk_size=8192 root=/dev/ram0 rw init=/sbin/init console=ttyAM0,115200n8 cfg.uart=1",
        display="none",
        serial_log=qemu_workdir / "serial.log",
        timeout_s=35.0,
    )
    runner.start()
    try:
        runner.wait_for_serial(r"(#|\$ )", timeout_s=30.0)
        runner.send_serial("lsmod; echo LSMOD_DONE\n")
        res = runner.wait_for_serial("LSMOD_DONE", timeout_s=10.0)
        assert_clean_linux_serial(res.serial_output)
        for mod in ("devno", "dmac", "ldec", "emmc"):
            assert mod in res.serial_output, f"Module {mod!r} missing from lsmod:\n{res.serial_output}"
    finally:
        try:
            runner.stop()
        except Exception:
            pass


def test_stock_initrd_interactive_ash_prompt(
    qemu_runner_cls,
    boot_stub_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T1-E4: Interactive /bin/ash shell responds to command sent over UART0."""
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    runner = runner_cls(
        kernel=kern,
        initrd=dumps_dir / "firmware" / "initrd.img",
        append="mem=1G@0 ramdisk_size=8192 root=/dev/ram0 rw init=/sbin/init console=ttyAM0,115200n8 cfg.uart=1",
        display="none",
        serial_log=qemu_workdir / "serial.log",
        timeout_s=35.0,
    )
    runner.start()
    try:
        runner.wait_for_serial(r"(#|\$ )", timeout_s=30.0)
        runner.send_serial("echo E2E_SHELL_ALIVE\n")
        res = runner.wait_for_serial("E2E_SHELL_ALIVE", timeout_s=10.0)
        assert not res.timed_out
        assert "E2E_SHELL_ALIVE" in res.serial_output
    finally:
        try:
            runner.stop()
        except Exception:
            pass


def test_stock_initrd_version_txt_present(
    qemu_runner_cls,
    boot_stub_mod,
    dumps_dir: Path,
    qemu_workdir: Path,
) -> None:
    """T1-E5: /version.txt or /initrd/version.txt reports firmware tag 30110_05.2025031501."""
    runner_cls, _ = qemu_runner_cls
    kern = prepare_stock_kernel_with_boot_stub(
        boot_stub_mod, dumps_dir / "firmware" / "vmlinux.bin", qemu_workdir / "artifacts"
    )
    runner = runner_cls(
        kernel=kern,
        initrd=dumps_dir / "firmware" / "initrd.img",
        append="mem=1G@0 ramdisk_size=8192 root=/dev/ram0 rw init=/sbin/init console=ttyAM0,115200n8 cfg.uart=1",
        display="none",
        serial_log=qemu_workdir / "serial.log",
        timeout_s=35.0,
    )
    runner.start()
    try:
        runner.wait_for_serial(r"(#|\$ )", timeout_s=30.0)
        runner.send_serial("cat /version.txt 2>/dev/null || cat /initrd/version.txt; echo VER_DONE\n")
        res = runner.wait_for_serial("VER_DONE", timeout_s=10.0)
        assert "30110_05.2025031501" in res.serial_output
    finally:
        try:
            runner.stop()
        except Exception:
            pass


# Stock storage regressions: see test_stock_milestones.py (M2).


# =============================================================================
# Area G — Feature #7: VPH / OSD0 (0xf3441300) Display Device
# =============================================================================


def test_osd0_frame_completion_3_to_2(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T1-G1: Writing 3 to OSD0 +0x00 transitions 3->2 on frame completion."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "osd0_flip",
        UART0_PROBE_C_PRELUDE
        + """
void probe_main(void) {
    mmio_w32(0xF2403100U, 0x80001030U);
    mmio_w32(0xF2403100U, 0x00001030U);
    mmio_w32(0xF3445000U, 0x00010114U);
    mmio_w32(0xF3446000U, 0x00000000U);
    mmio_w32(0xF3440144U, 0x00000002U);
    mmio_w32(0xF3440404U, 0x00000000U);
    mmio_w32(0xF344042CU, 480U);
    mmio_w32(0xF3441320U, 0x25000000U);
    mmio_w32(0xF3441324U, 1280U);
    mmio_w32(0xF3441348U, 1280U);
    mmio_w32(0xF344132CU, 479U);
    mmio_w32(0xF3441300U, 3U);
    uint32_t t0 = mmio_r32(0xF240310CU);
    while (mmio_r32(0xF3441300U) != 2U) {
        if ((mmio_r32(0xF240310CU) - t0) > 2000000U) {
            uart_puts("OSD0_FLIP_TMO\\n");
            return;
        }
    }
    uart_puts("OSD0_FLIP_OK\\n");
}
""",
    )
    res = run_probe_with_runner(runner_cls, kernel=probe, workdir=qemu_workdir, wait_pattern="OSD0_FLIP_", timeout_s=8.0)
    assert not res.timed_out
    assert "OSD0_FLIP_OK" in res.serial_output


def test_osd0_vsync_irq_102_50hz(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T1-G2: VPH VSYNC raises GIC IRQ 102 at ~50 Hz (~10 ticks per 200 ms virtual time)."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "vsync_irq102",
        UART0_PROBE_C_PRELUDE
        + """
static volatile uint32_t vsync_cnt = 0;
void probe_irq_handler(void) {
    uint32_t iar = mmio_r32(0xF800010CU);
    if ((iar & 0x3FFU) == 102U) {
        vsync_cnt++;
    }
    mmio_w32(0xF8000110U, iar);
}
void probe_main(void) {
    mmio_w32(0xF2403100U, 0x80001030U);
    mmio_w32(0xF2403100U, 0x00001030U);
    mmio_w32(0xF8001000U, 1U);
    mmio_w32(0xF8000104U, 0xFFU);
    mmio_w32(0xF8000100U, 1U);
    mmio_w32(0xF8001100U + (102U / 32U) * 4U, 1U << (102U % 32U));
    mmio_w32(0xF3445000U, 0x00010114U);
    mmio_w32(0xF3440144U, 0x00000002U);
    mmio_w32(0xF3441320U, 0x25000000U);
    mmio_w32(0xF3441324U, 1280U);
    mmio_w32(0xF3441348U, 1280U);
    mmio_w32(0xF344132CU, 479U);
    mmio_w32(0xF3441300U, 3U);
    __asm__ volatile("cpsie i");
    uint32_t t0 = mmio_r32(0xF240310CU);
    while ((mmio_r32(0xF240310CU) - t0) < 800000U) {
        if (mmio_r32(0xF3441300U) == 2U) mmio_w32(0xF3441300U, 3U);
    }
    uart_puts("VSYNC_CNT=");
    uart_puthex(vsync_cnt);
    uart_puts("\\n");
}
""",
        with_irq_vector=True,
    )
    res = run_probe_with_runner(runner_cls, kernel=probe, workdir=qemu_workdir, wait_pattern="VSYNC_CNT=", timeout_s=8.0)
    assert not res.timed_out
    m = re.search(r"VSYNC_CNT=([0-9a-fA-F]{8})", res.serial_output)
    assert m is not None, res.serial_output
    cnt = int(m.group(1), 16)
    assert 6 <= cnt <= 14, f"Expected ~10 VSYNC IRQs in 200 ms (50 Hz), got {cnt}"


def test_osd0_solid_color_rgba4444_scanout(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T1-G3: Solid 0xF00F RGBA4444 framebuffer scans out as RGB (255, 0, 0) in QMP screendump."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "osd0_solid_red",
        UART0_PROBE_C_PRELUDE
        + """
void probe_main(void) {
    volatile uint16_t *fb = (volatile uint16_t *)0x25000000U;
    for (uint32_t i = 0; i < 640U * 480U; i++) fb[i] = 0xF00FU;
    mmio_w32(0xF3445000U, 0x00010114U);
    mmio_w32(0xF3440144U, 0x00000002U);
    mmio_w32(0xF3440404U, 0U);
    mmio_w32(0xF344042CU, 480U);
    mmio_w32(0xF3441320U, 0x25000000U);
    mmio_w32(0xF3441324U, 1280U);
    mmio_w32(0xF3441348U, 1280U);
    mmio_w32(0xF344132CU, 479U);
    mmio_w32(0xF3441300U, 3U);
    uart_puts("RED_READY\\n");
}
""",
    )
    out_png = qemu_workdir / "captures" / "solid_red.png"
    res, _ = run_qemu_and_qmp_capture(runner_cls, kernel=probe, workdir=qemu_workdir, out_png=out_png, wait_s=1.0)
    assert "RED_READY" in res.serial_output
    rgb = verify_png_frame(out_png, expected_size=(640, 480), min_distinct_colors=1)
    assert tuple(int(v) for v in rgb[240, 320]) == (255, 0, 0)
    assert np.all(rgb == (255, 0, 0)), "Expected uniform RGB(255,0,0) across entire 640x480 frame"


def test_osd0_color_bars_pattern(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T1-G4: 4-band RGBA4444 pattern scans out exact Red/Green/Blue/White regions."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "osd0_4bars",
        UART0_PROBE_C_PRELUDE
        + """
void probe_main(void) {
    static const uint16_t cols[4] = {0xF00FU, 0x0F0FU, 0x00FFU, 0xFFFFU};
    volatile uint16_t *fb = (volatile uint16_t *)0x25000000U;
    for (uint32_t y = 0; y < 480U; y++) {
        for (uint32_t x = 0; x < 640U; x++) {
            fb[y * 640U + x] = cols[x / 160U];
        }
    }
    mmio_w32(0xF3445000U, 0x00010114U);
    mmio_w32(0xF3440144U, 0x00000002U);
    mmio_w32(0xF3440404U, 0U);
    mmio_w32(0xF344042CU, 480U);
    mmio_w32(0xF3441320U, 0x25000000U);
    mmio_w32(0xF3441324U, 1280U);
    mmio_w32(0xF3441348U, 1280U);
    mmio_w32(0xF344132CU, 479U);
    mmio_w32(0xF3441300U, 3U);
    uart_puts("BARS_READY\\n");
}
""",
    )
    out_png = qemu_workdir / "captures" / "bars4.png"
    res, _ = run_qemu_and_qmp_capture(runner_cls, kernel=probe, workdir=qemu_workdir, out_png=out_png, wait_s=1.0)
    assert "BARS_READY" in res.serial_output
    rgb = verify_png_frame(out_png, expected_size=(640, 480), min_distinct_colors=4)
    expected = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]
    for i, exp in enumerate(expected):
        assert tuple(int(v) for v in rgb[240, i * 160 + 80]) == exp


def test_osd0_double_buffer_page_flip(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T1-G5: Alternating OSD0 +0x20 between 0x25000000 (red) and 0x25096000 (blue) flips scanout."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "osd0_dblbuf",
        UART0_PROBE_C_PRELUDE
        + """
void probe_main(void) {
    volatile uint16_t *fb0 = (volatile uint16_t *)0x25000000U;
    volatile uint16_t *fb1 = (volatile uint16_t *)0x25096000U;
    for (uint32_t i = 0; i < 640U * 480U; i++) {
        fb0[i] = 0xF00FU;
        fb1[i] = 0x00FFU;
    }
    mmio_w32(0xF2403100U, 0x80001030U);
    mmio_w32(0xF2403100U, 0x00001030U);
    mmio_w32(0xF3445000U, 0x00010114U);
    mmio_w32(0xF3440144U, 0x00000002U);
    mmio_w32(0xF3440404U, 0U);
    mmio_w32(0xF344042CU, 480U);
    mmio_w32(0xF3441320U, 0x25000000U);
    mmio_w32(0xF3441324U, 1280U);
    mmio_w32(0xF3441348U, 1280U);
    mmio_w32(0xF344132CU, 479U);
    mmio_w32(0xF3441300U, 3U);
    while (mmio_r32(0xF3441300U) != 2U) {}
    uart_puts("FRAME1_RED\\n");
    uint32_t t0 = mmio_r32(0xF240310CU);
    while ((mmio_r32(0xF240310CU) - t0) < 2000000U) {}
    mmio_w32(0xF3441320U, 0x25096000U);
    mmio_w32(0xF3441300U, 3U);
    while (mmio_r32(0xF3441300U) != 2U) {}
    uart_puts("FRAME2_BLUE\\n");
}
""",
    )
    runner = runner_cls(
        kernel=probe,
        display="none",
        serial_log=qemu_workdir / "serial.log",
        qmp_port=free_tcp_port(),
        timeout_s=15.0,
    )
    f1 = qemu_workdir / "captures" / "frame1.png"
    f2 = qemu_workdir / "captures" / "frame2.png"
    runner.start()
    try:
        runner.wait_for_serial("FRAME1_RED", timeout_s=8.0)
        runner.capture_osd0_png(f1)
        runner.wait_for_serial("FRAME2_BLUE", timeout_s=8.0)
        runner.capture_osd0_png(f2)
        runner.stop()
    finally:
        try:
            runner.stop()
        except Exception:
            pass
    rgb1 = verify_png_frame(f1, expected_size=(640, 480), min_distinct_colors=1)
    rgb2 = verify_png_frame(f2, expected_size=(640, 480), min_distinct_colors=1)
    assert tuple(int(v) for v in rgb1[240, 320]) == (255, 0, 0)
    assert tuple(int(v) for v in rgb2[240, 320]) == (0, 0, 255)


# =============================================================================
# Area H — Feature #8: Framebuffer Capture (PNG) & Input Stubs (ADC0/1, GPIO)
# =============================================================================


def test_runner_capture_osd0_png_dimensions(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T1-H1: QemuRunner.capture_osd0_png emits valid 640x480 PNG from rtos_display ZVOS."""
    runner_cls, _ = qemu_runner_cls
    rtos_bin = build_zvos_payload(qemu_workdir / "zvos_disp", "rtos_display.S", display=True)
    elf = build_zvos_baremetal_elf(qemu_workdir / "zvos_disp", rtos_bin, name="rtos_disp")
    out_png = qemu_workdir / "captures" / "osd0.png"
    _, _ = run_qemu_and_qmp_capture(runner_cls, kernel=elf, workdir=qemu_workdir, out_png=out_png, wait_s=1.2)
    assert out_png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    rgb = verify_png_frame(out_png, expected_size=(640, 480), min_distinct_colors=8)
    verify_rtos_display_frame(rgb)


def test_adc1_idle_read_0x3ff(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T1-H2: ADC1 (0xf2407000) clears BUSY and reads idle 0x3FF on channels B0 and B3."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "adc1_idle",
        UART0_PROBE_C_PRELUDE
        + """
static uint16_t adc1_read(uint32_t ch) {
    mmio_w16(0xF2407000U, (uint16_t)(1U << ch));
    mmio_w16(0xF2407004U, 1U);
    for (uint32_t i = 0; i < 10000U; i++) {
        if ((mmio_r16(0xF2407010U) & 0x11U) == 0U) break;
    }
    return mmio_r16(0xF2407014U + ch * 4U);
}
void probe_main(void) {
    mmio_w16(0xF2407008U, 0U);
    mmio_w16(0xF2407044U, 0xFE03U);
    mmio_w16(0xF2407000U, 1U << 3);
    mmio_w16(0xF2407048U, 0x2FU);
    mmio_w16(0xF240700CU, 0U);
    mmio_w16(0xF2407008U, 1U);
    uint16_t b0 = adc1_read(0U);
    uint16_t b3 = adc1_read(3U);
    uart_puts("ADC1_B0="); uart_puthex(b0);
    uart_puts(" ADC1_B3="); uart_puthex(b3); uart_puts("\\n");
}
""",
    )
    res = run_probe_with_runner(runner_cls, kernel=probe, workdir=qemu_workdir, wait_pattern="ADC1_B3=", timeout_s=8.0)
    assert not res.timed_out
    assert "ADC1_B0=000003ff" in res.serial_output
    assert "ADC1_B3=000003ff" in res.serial_output


def test_adc1_key_injection_ok_and_dpad(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T1-H3: Host stimulus on ADC1 B3 navigates os_shell (DOWN -> OK launches Fire mode)."""
    runner_cls, _ = qemu_runner_cls
    rtos_bin = build_zvos_payload(qemu_workdir / "zvos_shell", "os_shell.c", display=True)
    elf = build_zvos_baremetal_elf(qemu_workdir / "zvos_shell", rtos_bin, name="os_shell")
    runner = runner_cls(
        kernel=elf,
        display="none",
        serial_log=qemu_workdir / "serial.log",
        qmp_port=free_tcp_port(),
        timeout_s=20.0,
    )
    p_init = qemu_workdir / "captures" / "status_init.png"
    p_fire = qemu_workdir / "captures" / "fire_launched.png"
    runner.start()
    try:
        time.sleep(1.0)
        runner.capture_osd0_png(p_init)
        rgb_init = verify_png_frame(p_init, expected_size=(640, 480), min_distinct_colors=4)
        verify_os_shell_status_frame(rgb_init, expected_sel=0, has_clip=False)

        # Press OK (0x000 on ADC1 B3) held across >= 2 50Hz frames (~40ms+) to launch Fire
        drive_adc_gpio_stimulus(runner, adc1_b3=0x000)
        time.sleep(0.35)
        drive_adc_gpio_stimulus(runner, adc1_b3=0x3FF)
        time.sleep(0.25)
        runner.capture_osd0_png(p_fire)
        runner.stop()
    finally:
        try:
            runner.stop()
        except Exception:
            pass
    rgb_fire = verify_png_frame(p_fire, expected_size=(640, 480), min_distinct_colors=2)
    assert not np.array_equal(rgb_init, rgb_fire), "Expected OSD0 frame to change after OK launches Fire"
    # Fire background is 0x000F (0,0,0) instead of Status banner (17,34,68)
    assert tuple(int(v) for v in rgb_fire[10, 10]) == (0, 0, 0)


def test_adc0_key_and_adc1_b0_delete(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T1-H4: Injecting DELETE (ADC1 B0 <= 0x5B) exits Fire mode back to Status menu."""
    runner_cls, _ = qemu_runner_cls
    rtos_bin = build_zvos_payload(qemu_workdir / "zvos_shell", "os_shell.c", display=True)
    elf = build_zvos_baremetal_elf(qemu_workdir / "zvos_shell", rtos_bin, name="os_shell")
    runner = runner_cls(
        kernel=elf,
        display="none",
        serial_log=qemu_workdir / "serial.log",
        qmp_port=free_tcp_port(),
        timeout_s=20.0,
    )
    p_exit = qemu_workdir / "captures" / "back_to_status.png"
    runner.start()
    try:
        time.sleep(0.8)
        drive_adc_gpio_stimulus(runner, adc1_b3=0x000)  # OK -> Fire
        time.sleep(0.3)
        drive_adc_gpio_stimulus(runner, adc1_b3=0x3FF)
        time.sleep(0.2)
        drive_adc_gpio_stimulus(runner, adc1_b0=0x000)  # DELETE -> exit Fire
        time.sleep(0.35)
        drive_adc_gpio_stimulus(runner, adc1_b0=0x3FF)
        time.sleep(0.2)
        runner.capture_osd0_png(p_exit)
        runner.stop()
    finally:
        try:
            runner.stop()
        except Exception:
            pass
    rgb_exit = verify_png_frame(p_exit, expected_size=(640, 480), min_distinct_colors=4)
    verify_os_shell_status_frame(rgb_exit, expected_sel=0, has_clip=False)


def test_gpio_g00_mode_dial_and_led_set_clr(qemu_runner_cls, qemu_workdir: Path) -> None:
    """T1-H5: GPIO0 LED SET/CLR (0xf2910044/48) and G00 RDATA (0xf2910010) reflect injected state."""
    runner_cls, _ = qemu_runner_cls
    probe = build_baremetal_arm_probe(
        qemu_workdir / "artifacts",
        "gpio_probe",
        UART0_PROBE_C_PRELUDE
        + """
void probe_main(void) {
    mmio_w32(0xF2910044U, 1U);
    mmio_w32(0xF2910048U, 1U);
    uart_puts("GPIO_LED_OK\\n");
    for (uint32_t i = 0; i < 4000000U; i++) {
        uint32_t g00 = mmio_r32(0xF2910010U);
        if (g00 & 0x400U) {
            uart_puts("MODE_KEY_OK\\n");
            break;
        }
    }
    uart_puts("GPIO_DONE\\n");
}
""",
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
        runner.wait_for_serial("GPIO_LED_OK", timeout_s=5.0)
        drive_adc_gpio_stimulus(runner, gpio_g00=0x400)
        res = runner.wait_for_serial("GPIO_DONE", timeout_s=8.0)
        assert "GPIO_LED_OK" in res.serial_output
        assert "MODE_KEY_OK" in res.serial_output
    finally:
        try:
            runner.stop()
        except Exception:
            pass


# =============================================================================
# Area I — Feature #9: av-cam.bin (LIRO RTOS) Execution & bootrom
# =============================================================================


def test_avcam_header_and_bootrom_dump_contract(dumps_dir: Path) -> None:
    """T1-I1: Verify read-only av-cam.bin ('ORIL' v4, 17289388 B) and bootrom (24576 B) contracts."""
    avcam = dumps_dir / "firmware" / "av-cam.bin"
    bootrom = dumps_dir / "firmware" / "bootrom"
    assert avcam.stat().st_size == 17_289_388
    assert bootrom.stat().st_size == 24_576
    with avcam.open("rb") as fh:
        hdr = fh.read(16)
    branch_insn, magic, version = struct.unpack_from("<III", hdr, 0)
    assert (branch_insn >> 24) == 0xEA, f"Expected ARM B instruction at +0, got 0x{branch_insn:08x}"
    assert magic == 0x4C49524F, f"Expected 'ORIL' magic, got 0x{magic:08x}"
    assert version == 4, f"Expected LIRO version 4, got {version}"

    brom_bytes = bootrom.read_bytes()
    assert brom_bytes[:4] == bytes.fromhex("140000ea")
    assert b"Astra Loader1" in brom_bytes


# Stock LIRO regressions: see test_stock_milestones.py (M4).
