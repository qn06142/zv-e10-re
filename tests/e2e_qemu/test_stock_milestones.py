"""Stock initrd/eMMC (M2) and bootloader/LIRO (M4) regression tests."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from emulator.runner import DEFAULT_QEMU_BIN, QemuRunner, verify_zve10_qemu_unmodified
from emulator.stock_boot import prepare_stock_boot
from emulator.storage import DEFAULT_DUMPS_DIR

pytestmark = [pytest.mark.e2e_qemu, pytest.mark.skipif(
    not (DEFAULT_QEMU_BIN.is_file() and (DEFAULT_DUMPS_DIR / "firmware/initrd.img").is_file()),
    reason="Built QEMU and local stock firmware capture are required",
)]


def _digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@pytest.fixture(scope="module")
def staged_boot(tmp_path_factory):
    # Include every dump consumed by staging. Hash before and after the guest
    # runs, so accidental writes to reference files cannot pass unnoticed.
    inputs = [DEFAULT_DUMPS_DIR / rel for rel in (
        "firmware/vmlinux.bin", "firmware/initrd.img", "trees/setting.tgz", "trees/etc.tgz",
    )]
    for name in ("nflasha3.img", "nflasha7.img", "nflasha15.img"):
        source = DEFAULT_DUMPS_DIR / name
        inputs.append(source if source.is_file() else DEFAULT_DUMPS_DIR / "card" / name)
    verify_zve10_qemu_unmodified()
    before = {p: _digest(p) for p in inputs}
    try:
        yield prepare_stock_boot(work_dir=tmp_path_factory.mktemp("stock_boot"))
    finally:
        assert {p: _digest(p) for p in inputs} == before, "Read-only firmware inputs changed"
        verify_zve10_qemu_unmodified()


@pytest.fixture
def stock_guest(staged_boot, qemu_workdir):
    with QemuRunner(**staged_boot.runner_kwargs(), serial_log=qemu_workdir / "serial.log",
                    timeout_s=45) as runner:
        runner.wait_for_serial(r"(?m)^/ # ", regex=True)
        yield runner


def _shell(runner, command, marker):
    start = len(runner.serial_output)
    runner.send_serial(command + f"; printf '\\n{marker}=%s\\n' $?\n")
    # Anchored output cannot match the terminal's echo of the command.
    result = runner.wait_for_serial(rf"(?m)^{marker}=\d+\r?$", regex=True, start_pos=start, timeout_s=12)
    output = runner.serial_output[start:]
    assert result.rstrip("\r") == marker + "=0", output
    for error in ("Kernel panic", "Unable to handle kernel", "Oops:"):
        assert error not in runner.serial_output, runner.serial_output[-4000:]
    return output


def test_m2_stock_initrd_mounts_and_writable_log(stock_guest):
    r = stock_guest
    output = _shell(r, "mount", "M2_MOUNTS")
    assert "eMMC: HS200 mode" in r.serial_output
    assert "SMP: Total of 4 processors activated" in r.serial_output
    for slot, mount in ((7, "/"), (15, "/usr"), (10, "/etc"), (10, "/tmp"),
                        (2, "/setting"), (3, "/system"), (11, "/log"),
                        (12, "/cert"), (18, "/lens")):
        assert f"/dev/nflasha{slot} on {mount} type " in output, output
    _shell(r, "test -s /setting/Backup.bin && test -s /setting/DmmConfig.bin "
           "&& test -s /system/av-cam.bin && test -f /usr/kmod/liro.ko "
           "&& test -f /root/common.src && test -d /initrd "
           "&& test -f /usr/bin/bootin.elf && test -f /usr/bin/im.elf "
           "&& test -f /etc/toprc "
           "&& echo stock-log-ok > /log/e2e.txt "
           "&& test \"$(cat /log/e2e.txt)\" = stock-log-ok", "M2_FILES")


def test_m4_backup_udate_and_liro_entry_main(stock_guest, staged_boot, qemu_workdir):
    r = stock_guest
    # Confirm the bootloader copy survived kernel startup in reserved RAM.
    raw = staged_boot.backup_image.read_bytes()
    assert r.pmemsave(staged_boot.backup_address, len(raw), qemu_workdir / "backup.ram") == raw
    modules = (
        "osal_utm.ko", "osal_uipc.ko", "utimer.ko", "backup.ko Backup_load=0",
        "osal_ulogio.ko ulogio_initfile=/setting/ulogio.bin", "udate.ko",
        "dmm.ko DmmConfig=/setting/DmmConfig.bin", "dma330.ko",
        "liro.ko adr=0x035c6000 fn=/system/av-cam.bin load=1 debug=1",
    )
    _shell(r, " && ".join("insmod /usr/kmod/" + m for m in modules[:-1]), "M4_DEPS")
    listing = _shell(r, "lsmod", "M4_LSMOD")
    for name in ("backup", "udate", "dmm", "dma330"):
        assert re.search(rf"(?m)^{name}\s+", listing), listing
    # LIRO starts asynchronously and UART shell responsiveness after entry_main
    # is not established. Verify execution itself, without assuming a prompt.
    start = len(r.serial_output)
    r.send_serial("insmod /usr/kmod/" + modules[-1] + "\n")
    r.wait_for_serial("end entry_main", start_pos=start)
    assert "0 -> 635c6000 : 0 107d0ac loaded (OK)" in r.serial_output
    assert "end entry_pre" in r.serial_output
    assert "backup_init() error" not in r.serial_output
    assert "ERROR:arch_phys_to_noncache" not in r.serial_output
    for error in ("Kernel panic", "Unable to handle kernel", "Oops:"):
        assert error not in r.serial_output
