"""Minimal real-execution & R3-guard tests for pmca-re QEMU ZV-E10 emulator."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from PIL import Image
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from emulator import (
    DEFAULT_QEMU_BIN,
    DEFAULT_ZVE10_QEMU_DIR,
    EXPECTED_ZVE10_QEMU_HEAD,
    QemuRunner,
    R3ViolationError,
    rgba4444_to_png,
    verify_zve10_qemu_unmodified,
)
from emulator.boot_stub import (
    DEFAULT_STOCK_CMDLINE,
    DEFAULT_STOCK_VMLINUX,
    prepare_stock_kernel_uimage,
    prepare_test_initrd,
)


def test_r3_guard_zve10_qemu_unmodified() -> None:
    if not DEFAULT_ZVE10_QEMU_DIR.is_dir():
        pytest.skip("Reference zve10-qemu directory not present")
    status = verify_zve10_qemu_unmodified(DEFAULT_ZVE10_QEMU_DIR)
    assert status.ok is True
    assert status.head == EXPECTED_ZVE10_QEMU_HEAD
    assert status.unexpected_dirty == ()


def test_r3_guard_detects_unexpected_modification(tmp_path: Path) -> None:
    fake_repo = tmp_path / "fake_zve10_qemu"
    fake_repo.mkdir()
    subprocess.run(["git", "-C", str(fake_repo), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(fake_repo), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(fake_repo), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )
    (fake_repo / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(fake_repo), "add", "README.md"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(fake_repo), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    (fake_repo / "tampered.txt").write_text("oops\n", encoding="utf-8")

    with pytest.raises(R3ViolationError):
        verify_zve10_qemu_unmodified(fake_repo)


def test_qemu_runner_command_env_and_rgba4444(tmp_path: Path) -> None:
    runner = QemuRunner(
        qemu_bin=tmp_path / "bin" / "qemu-system-arm.exe",
        kernel=tmp_path / "uImage",
        initrd=tmp_path / "initrd.cpio",
        append="console=ttyAM0,115200n8",
        smp=4,
        memory="1024",
        display="vnc",
        device_loader=[{"addr": 0x635C6000, "file": "av-cam.bin"}],
    )
    cmd = runner.build_command(serial_port=45001, qmp_port=45002)
    assert "-M" in cmd and cmd[cmd.index("-M") + 1] == "zve10"
    assert "-smp" in cmd and cmd[cmd.index("-smp") + 1] == "4"
    assert "-vnc" in cmd and cmd[cmd.index("-vnc") + 1] == "127.0.0.1:0"
    assert "-serial" in cmd and "tcp:127.0.0.1:45001,server=on,wait=on" in cmd
    assert "-qmp" in cmd and "tcp:127.0.0.1:45002,server=on,wait=off" in cmd
    assert any("addr=0x635c6000,file=av-cam.bin" in arg for arg in cmd)

    old_path = os.environ.get("PATH")
    env = runner.build_env()
    assert env["PATH"].startswith(str((tmp_path / "bin")))
    assert os.environ.get("PATH") == old_path

    # 2x2 RGBA4444: red (0xF00F), green (0x0F0F), blue (0x00FF), white (0xFFFF)
    raw = (0xF00F).to_bytes(2, "little") + (0x0F0F).to_bytes(2, "little") + (0x00FF).to_bytes(2, "little") + (0xFFFF).to_bytes(2, "little")
    out_png = rgba4444_to_png(raw, tmp_path / "osd0.png", width=2, height=2)
    with Image.open(out_png) as img:
        assert img.size == (2, 2)
        assert img.getpixel((0, 0)) == (255, 0, 0, 255)
        assert img.getpixel((1, 0)) == (0, 255, 0, 255)
        assert img.getpixel((0, 1)) == (0, 0, 255, 255)
        assert img.getpixel((1, 1)) == (255, 255, 255, 255)


@pytest.mark.skipif(not DEFAULT_QEMU_BIN.is_file(), reason="QEMU binary not built yet")
def test_qemu_standalone_version_mtree_and_qmp_smoke(tmp_path: Path) -> None:
    clean_env = {
        "SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
        "WINDIR": os.environ.get("WINDIR", r"C:\Windows"),
        "PATH": r"C:\Windows\System32;C:\Windows",
    }
    ver = subprocess.run(
        [str(DEFAULT_QEMU_BIN), "--version"],
        env=clean_env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "11.1.2" in ver.stdout

    machines = subprocess.run(
        [str(DEFAULT_QEMU_BIN), "-M", "help"],
        env=clean_env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "zve10" in machines.stdout

    with QemuRunner(cpu=None, extra_args=["-S"], timeout_s=15.0) as runner:
        status = runner.qmp_command("query-status")
        assert status["status"] in ("prelaunch", "paused")
        mtree = runner.qmp_command("human-monitor-command", {"command-line": "info mtree"})
        assert "zve10.ram" in mtree
        assert "zve10.ddr1" in mtree
        assert "zve10.esram" in mtree
        assert "sony-hwtimer" in mtree
        mem = runner.pmemsave(0x00000000, 64, tmp_path / "ram0.bin", pause=True)
        assert len(mem) == 64
        result = runner.stop()
    assert result.returncode == 0


@pytest.mark.skipif(
    not (DEFAULT_QEMU_BIN.is_file() and DEFAULT_STOCK_VMLINUX.is_file()),
    reason="QEMU binary or stock vmlinux.bin missing",
)
@pytest.mark.parametrize("smp", [1, 4])
def test_stock_vmlinux_boot_uart0(tmp_path: Path, smp: int) -> None:
    uimage = prepare_stock_kernel_uimage(out_path=tmp_path / "vmlinux_atags.uImage")
    initrd = prepare_test_initrd(
        out_path=tmp_path / "test_initrd.cpio",
        banner="HELLO_ZVE10_STOCK_KERN\n",
    )
    serial_log = tmp_path / f"serial_smp{smp}.log"

    runner = QemuRunner(
        cpu=None,
        smp=smp,
        memory="1024",
        kernel=uimage,
        initrd=initrd,
        append=DEFAULT_STOCK_CMDLINE,
        serial_log=serial_log,
        timeout_s=20.0,
    )
    result = runner.run(wait_pattern="HELLO_ZVE10_STOCK_KERN", timeout_s=20.0)
    assert result.timed_out is False, f"Timed out (smp={smp}); serial:\n{result.serial_output}"
    assert "Linux version 3.0.27_nl-rt106+" in result.serial_output
    assert "HELLO_ZVE10_STOCK_KERN" in result.serial_output
    assert "Kernel panic" not in result.serial_output
    if smp == 4:
        assert "SMP: Total of 4 processors activated" in result.serial_output
    assert serial_log.is_file()
    assert "HELLO_ZVE10_STOCK_KERN" in serial_log.read_text(encoding="utf-8", errors="replace")


@pytest.mark.skipif(not DEFAULT_QEMU_BIN.is_file(), reason="QEMU binary not built yet")
def test_m3_osd_scanout_adc_gpio(tmp_path: Path) -> None:
    frame = tmp_path / "quadrants.rgba4444"
    top = b"\x0f\xf0" * 320 + b"\x0f\x0f" * 320
    bottom = b"\xff\x00" * 320 + b"\xff\xff" * 320
    frame.write_bytes(top * 240 + bottom * 240)
    frame_pa = 0x04A00000
    with QemuRunner(cpu=None, extra_args=["-S"],
                    device_loader=[{"addr": frame_pa, "file": frame, "force-raw": "on"}]) as runner:
        mtree = runner.qmp_command("human-monitor-command", {"command-line": "info mtree"})
        for name in ("sony-vph-osd0", "zve10-adc0", "zve10-adc1", "zve10-gpio", "sony-f-sdh30"):
            assert name in mtree
        for captured in (runner.capture_screendump(tmp_path / "console.png"),
                         runner.capture_osd0_png(tmp_path / "framebuffer.png", fb_addr=frame_pa)):
            with Image.open(captured) as image:
                assert image.size == (640, 480)
                rgb = image.convert("RGB")
                assert [rgb.getpixel(p) for p in ((160, 120), (480, 120), (160, 360), (480, 360))] == [
                    (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255),
                ]
        for address, value in ((0xF2406010, 0), (0xF2406018, 4),
                               (0xF2406014, 0x3f0), (0xF240702c, 0x3f0),
                               (0xF2910000, 0x400), (0xF2910010, 0)):
            output = runner.qmp_command("human-monitor-command", {"command-line": f"xp /1wx {address:#x}"})
            assert int(output.split()[-1], 16) == value, output
        result = runner.stop()
    assert result.returncode == 0


def test_backup_loader_rejects_invalid_header_and_destination() -> None:
    from emulator.stock_boot import backup_load_address

    for data in (b"", bytes(256), b"bad header" * 40):
        with pytest.raises(ValueError, match="header"):
            backup_load_address(data)
    valid = bytearray(0x100)
    valid[:4] = (0x02e80000).to_bytes(4, "little")
    valid[4:8] = b"\xaa" * 4
    valid[12:16] = b"BK4\0"
    assert backup_load_address(valid) == 0x02e80000
    for address in (0, 0x02e80001, 0x048c5ffc, 0xf2000000):
        valid[:4] = address.to_bytes(4, "little")
        with pytest.raises(ValueError, match="arena"):
            backup_load_address(valid)


@pytest.mark.skipif(not DEFAULT_QEMU_BIN.is_file(), reason="QEMU binary not built yet")
@pytest.mark.parametrize("strict", [True, False])
def test_camera_and_menu_cpu_profiles(strict: bool) -> None:
    machine = "zve10" if strict else "zve10,strict-cpu=off"
    with QemuRunner(machine=machine, cpu=None, extra_args=["-S"]) as runner:
        assert runner.qmp_command("qom-get", {"path": "/machine", "property": "strict-cpu"}) is strict
        cpu = runner.qmp_command("query-cpus-fast")[0]["qom-path"]
        for name in ("neon", "vfp-d32"):
            assert runner.qmp_command("qom-get", {"path": cpu, "property": name}) is (not strict)
