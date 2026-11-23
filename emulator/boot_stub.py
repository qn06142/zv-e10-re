"""Stock ZV-E10 kernel staging, U-Boot uImage wrapping, and test initrd builder.

Non-destructively stages `.local/dumps/firmware/vmlinux.bin` into
`.local/emulator/work/` so QEMU `-M zve10` can boot the unmodified stock Sony
kernel (3.0.27_nl-rt106+, TEXT_OFFSET=0x108000) with ATAGs preserved at
0x00000100.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import stat
import struct
from typing import Iterable
import zlib

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STOCK_VMLINUX = REPO_ROOT / ".local" / "dumps" / "firmware" / "vmlinux.bin"
DEFAULT_WORK_DIR = REPO_ROOT / ".local" / "emulator" / "work"

EJ_HEAD_INIT_R2_OFFSET = 0x17024
STOCK_MVN_R2_0 = b"\x00\x20\xe0\xe3"       # 0xe3e02000: mvn r2, #0
PATCH_MOV_R2_0X100 = b"\x01\x2c\xa0\xe3"   # 0xe3a02c01: mov r2, #0x100

STOCK_KERNEL_LOAD_ADDR = 0x00108000
STOCK_KERNEL_ENTRY_ADDR = 0x00108000

UIMAGE_MAGIC = 0x27051956
IH_OS_LINUX = 5
IH_ARCH_ARM = 2
IH_TYPE_KERNEL = 2
IH_COMP_NONE = 0

DEFAULT_STOCK_CMDLINE = (
    "console=ttyAM0,115200n8 amba2.console=1 cfg.uart=1 "
    "mem=1G@0 ip=off rdinit=/init loglevel=8"
)


@dataclass(frozen=True)
class CpioEntry:
    name: str
    mode: int
    data: bytes = b""
    rdev_major: int = 0
    rdev_minor: int = 0
    uid: int = 0
    gid: int = 0


def build_uimage(
    payload: bytes,
    *,
    load_addr: int = STOCK_KERNEL_LOAD_ADDR,
    entry_addr: int = STOCK_KERNEL_ENTRY_ADDR,
    name: str = "zve10-stock-linux",
) -> bytes:
    """Wrap a raw ARM Linux Image in an uncompressed 64-byte U-Boot uImage header."""
    name_bytes = name.encode("ascii", errors="replace")[:32].ljust(32, b"\x00")
    data_crc = zlib.crc32(payload) & 0xFFFFFFFF
    hdr_zero = struct.pack(
        ">IIIIIIIBBBB32s",
        UIMAGE_MAGIC,
        0,
        0,
        len(payload),
        load_addr,
        entry_addr,
        data_crc,
        IH_OS_LINUX,
        IH_ARCH_ARM,
        IH_TYPE_KERNEL,
        IH_COMP_NONE,
        name_bytes,
    )
    hdr_crc = zlib.crc32(hdr_zero) & 0xFFFFFFFF
    hdr = struct.pack(
        ">IIIIIIIBBBB32s",
        UIMAGE_MAGIC,
        hdr_crc,
        0,
        len(payload),
        load_addr,
        entry_addr,
        data_crc,
        IH_OS_LINUX,
        IH_ARCH_ARM,
        IH_TYPE_KERNEL,
        IH_COMP_NONE,
        name_bytes,
    )
    return hdr + payload


def patch_stock_vmlinux_atags(vmlinux_bytes: bytes) -> bytes:
    """Verify and patch ej_head_init's `mvn r2, #0` to `mov r2, #0x100`."""
    end = EJ_HEAD_INIT_R2_OFFSET + 4
    if len(vmlinux_bytes) < end:
        raise ValueError(
            f"vmlinux.bin too small ({len(vmlinux_bytes)} bytes) to contain offset 0x{EJ_HEAD_INIT_R2_OFFSET:x}"
        )
    actual = vmlinux_bytes[EJ_HEAD_INIT_R2_OFFSET:end]
    if actual != STOCK_MVN_R2_0:
        raise ValueError(
            f"Unexpected instruction at 0x{EJ_HEAD_INIT_R2_OFFSET:x}: "
            f"expected {STOCK_MVN_R2_0.hex()}, got {actual.hex()}"
        )
    buf = bytearray(vmlinux_bytes)
    buf[EJ_HEAD_INIT_R2_OFFSET:end] = PATCH_MOV_R2_0X100
    return bytes(buf)


def prepare_stock_kernel_uimage(
    vmlinux_path: Path | str = DEFAULT_STOCK_VMLINUX,
    out_path: Path | str | None = None,
) -> Path:
    """Stage stock vmlinux.bin non-destructively into a QEMU-bootable uImage."""
    src = Path(vmlinux_path)
    if not src.is_file():
        raise FileNotFoundError(f"Stock vmlinux.bin not found: {src}")

    dst = Path(out_path) if out_path is not None else (DEFAULT_WORK_DIR / "vmlinux_atags.uImage")
    dst.parent.mkdir(parents=True, exist_ok=True)

    raw = src.read_bytes()
    patched = patch_stock_vmlinux_atags(raw)
    uimage = build_uimage(patched)

    if not dst.is_file() or dst.read_bytes() != uimage:
        dst.write_bytes(uimage)
    return dst


def build_arm_hello_init_elf(banner: str = "HELLO_ZVE10_STOCK_KERN\n") -> bytes:
    """Build a minimal static ARM EABI ELF `/init` binary that prints banner and pauses."""
    msg = banner.encode("utf-8")
    ehdr_size = 52
    phdr_size = 32
    base_vaddr = 0x00010000
    code_offset = ehdr_size + phdr_size

    # ARM EABI code (28 bytes) + 4-byte length word + msg bytes:
    #   0x00: mov r0, #1          (fd = stdout)
    #   0x04: add r1, pc, #20     (r1 = &msg at +0x20)
    #   0x08: ldr r2, [pc, #12]   (r2 = msg_len at +0x1c)
    #   0x0c: mov r7, #4          (__NR_write)
    #   0x10: swi #0
    #   0x14: mov r7, #29         (__NR_pause)
    #   0x18: b   0x10            (loop sys_pause forever without killing PID 1)
    #   0x1c: .word len(msg)
    #   0x20: msg...
    code = struct.pack(
        "<8I",
        0xE3A00001,
        0xE28F1014,
        0xE59F200C,
        0xE3A07004,
        0xEF000000,
        0xE3A0701D,
        0xEAFFFFFC,
        len(msg),
    )
    file_size = code_offset + len(code) + len(msg)

    ehdr = struct.pack(
        "<16sHHIIIIIHHHHHH",
        b"\x7fELF\x01\x01\x01\x00" + b"\x00" * 8,
        2,              # ET_EXEC
        40,             # EM_ARM
        1,              # EV_CURRENT
        base_vaddr + code_offset,
        ehdr_size,      # e_phoff
        0,              # e_shoff
        0x05000000,     # EF_ARM_EABI_VER5
        ehdr_size,
        phdr_size,
        1,              # e_phnum
        0,
        0,
        0,
    )
    phdr = struct.pack(
        "<IIIIIIII",
        1,              # PT_LOAD
        0,              # p_offset
        base_vaddr,     # p_vaddr
        base_vaddr,     # p_paddr
        file_size,      # p_filesz
        file_size,      # p_memsz
        5,              # PF_R | PF_X
        0x1000,         # p_align
    )
    return ehdr + phdr + code + msg


def build_cpio_newc(entries: Iterable[CpioEntry]) -> bytes:
    """Serialize entries into an SVR4 `newc` (070701) initramfs cpio archive."""
    chunks: list[bytes] = []
    ino = 1

    def _pad4(n: int) -> bytes:
        rem = n % 4
        return b"\x00" * ((4 - rem) % 4)

    def _emit(entry: CpioEntry, inode: int) -> None:
        name_bytes = entry.name.lstrip("/").encode("utf-8") + b"\x00"
        nlink = 2 if stat.S_ISDIR(entry.mode) else 1
        hdr = (
            "070701"
            f"{inode:08x}"
            f"{entry.mode:08x}"
            f"{entry.uid:08x}"
            f"{entry.gid:08x}"
            f"{nlink:08x}"
            f"{0:08x}"
            f"{len(entry.data):08x}"
            f"{0:08x}"
            f"{0:08x}"
            f"{entry.rdev_major:08x}"
            f"{entry.rdev_minor:08x}"
            f"{len(name_bytes):08x}"
            f"{0:08x}"
        ).encode("ascii")
        chunks.append(hdr)
        chunks.append(name_bytes)
        chunks.append(_pad4(len(hdr) + len(name_bytes)))
        if entry.data:
            chunks.append(entry.data)
            chunks.append(_pad4(len(entry.data)))

    for entry in entries:
        _emit(entry, ino)
        ino += 1

    _emit(CpioEntry(name="TRAILER!!!", mode=0), 0)
    total = sum(len(c) for c in chunks)
    rem = total % 512
    if rem:
        chunks.append(b"\x00" * (512 - rem))
    return b"".join(chunks)


def prepare_test_initrd(
    out_path: Path | str | None = None,
    banner: str = "HELLO_ZVE10_STOCK_KERN\n",
) -> Path:
    """Create a minimal initramfs cpio archive with /dev/console and ARM /init."""
    dst = Path(out_path) if out_path is not None else (DEFAULT_WORK_DIR / "test_initrd.cpio")
    dst.parent.mkdir(parents=True, exist_ok=True)

    init_elf = build_arm_hello_init_elf(banner=banner)
    cpio = build_cpio_newc(
        [
            CpioEntry(name="dev", mode=stat.S_IFDIR | 0o755),
            CpioEntry(
                name="dev/console",
                mode=stat.S_IFCHR | 0o600,
                rdev_major=5,
                rdev_minor=1,
            ),
            CpioEntry(name="init", mode=stat.S_IFREG | 0o755, data=init_elf),
        ]
    )
    if not dst.is_file() or dst.read_bytes() != cpio:
        dst.write_bytes(cpio)
    return dst
