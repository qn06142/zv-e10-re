"""Reproduce the stock bootloader's RAM setup for initrd + eMMC boots.

Firmware dumps and the external zve10-qemu checkout are read-only inputs.
All staged files belong to the supplied work directory.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from emulator.boot_stub import prepare_stock_kernel_uimage
from emulator.storage import DEFAULT_DUMPS_DIR, StagedStorage, load_tgz_tree, stage_storage

# The stock /setting/kemco.txt reserves the Backup/LIRO arena and creates
# uncached aliases for firmware-owned DDR. In particular udate accesses
# PA 0x200210e4 via arch_phys_to_noncache(), which otherwise returns NULL.
STOCK_INIT_CMDLINE = (
    "console=ttyAM0,115200n8 amba2.console=1 cfg.uart=1 "
    "mem=1G@0 root=/dev/ram0 rw init=/sbin/init ip=off loglevel=8 "
    "adrs_conv.null=Y cgroup_disable=memory "
    "memrsv=1M@0 memrsv=0x8000@0xF00000 "
    "memrsv=0x1A5E000@0x02E68000 memrsv=0xAEEB000@0x0A915000 "
    "memrsv=680M@0x15800000:uc "
    "mem=256M@0x80000000@1 memrsv=256M@0x80000000:uc"
)
BACKUP_ARENA_START = 0x02E68000
BACKUP_ARENA_END = BACKUP_ARENA_START + 0x1A5E000


def backup_load_address(data: bytes) -> int:
    """Read the BK4 bootloader destination, bounded by its reserved RAM arena."""
    if len(data) < 0x100 or data[4:8] != b"\xaa" * 4 or data[12:16] != b"BK4\0":
        raise ValueError("Expected a stock BK4 Backup.bin header")
    address = int.from_bytes(data[:4], "little")
    if address % 4 or not (BACKUP_ARENA_START <= address < address + len(data) <= BACKUP_ARENA_END):
        raise ValueError("Backup.bin does not fit in the reserved Backup/LIRO RAM arena")
    return address


@dataclass(frozen=True)
class StagedStockBoot:
    kernel: Path
    initrd: Path
    storage: StagedStorage
    backup_image: Path
    backup_address: int

    def runner_kwargs(self) -> dict[str, Any]:
        """Fresh runner arguments; snapshot keeps the staged eMMC reusable."""
        return {
            "cpu": None,
            "smp": 4,
            "memory": "1280",
            "kernel": self.kernel,
            "initrd": self.initrd,
            "append": STOCK_INIT_CMDLINE,
            "drives": [{"if": "none", "id": "emmc0", "format": "raw",
                        "file": self.storage.emmc_image, "snapshot": "on"}],
            "device_loader": [{"addr": self.backup_address, "file": self.backup_image,
                               "force-raw": "on"}],
        }


def prepare_stock_boot(
    *,
    work_dir: Path | str,
    dumps_dir: Path | str = DEFAULT_DUMPS_DIR,
    kernel_only: bool = True,
) -> StagedStockBoot:
    """Stage stock userspace boot, including the RAM assumed by Backup_load=0.

    kernel_only=True selects dmode=0 for an ash prompt. False preserves the
    normal setting partition; full application startup is still incomplete.
    Use matching setting.tgz and card dumps from the same camera capture.
    """
    dumps = Path(dumps_dir)
    initrd = dumps / "firmware" / "initrd.img"
    if not initrd.is_file():
        raise FileNotFoundError(initrd)
    setting = load_tgz_tree(dumps / "trees" / "setting.tgz", strip_prefix="setting")
    backup = setting.get("Backup.bin")
    if backup is None:
        raise ValueError("setting.tgz is missing Backup.bin")
    address = backup_load_address(backup)
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    backup_image = work / "Backup.bin"
    backup_image.write_bytes(backup)
    kernel = prepare_stock_kernel_uimage(
        vmlinux_path=dumps / "firmware" / "vmlinux.bin", out_path=work / "vmlinux.uImage"
    )
    storage = stage_storage(dumps_dir=dumps, work_dir=work / "storage",
                            kernel_only=kernel_only, include_usr=True)
    return StagedStockBoot(kernel, initrd, storage, backup_image, address)
