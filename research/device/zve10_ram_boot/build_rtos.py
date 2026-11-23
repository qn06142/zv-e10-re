"""Build and package a standalone ARM image for the ZV-E10 RAM loader."""
import argparse
import struct
import subprocess
import zlib
from pathlib import Path

from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parent
TOOLS = Path("C:/msys64/ucrt64/bin")
HEADER = struct.Struct("<8I")
MAGIC = int.from_bytes(b"ZVRT", "little")
VERSION = 1
MAX_IMAGE_BYTES = 1024 * 1024


def package_image(code, entry, *, display=False):
    if not 4 <= len(code) <= MAX_IMAGE_BYTES or len(code) % 4:
        raise ValueError("ARM image must be word aligned and within MAX_IMAGE_BYTES")
    if not 0 <= entry < len(code) or entry % 4:
        raise ValueError("entry must be an aligned offset inside the image")
    return HEADER.pack(
        MAGIC, VERSION, HEADER.size, len(code), entry, zlib.crc32(code), int(display), 0
    ) + code


def extract_c_image(elf):
    base_vaddr = 0x81000000
    alloc_sections = [
        sec for sec in elf.iter_sections()
        if (sec["sh_flags"] & 2) and sec["sh_type"] != "SHT_NOBITS" and sec["sh_size"] > 0
    ]
    if not alloc_sections:
        raise ValueError("no allocated sections in ELF")
    end_vaddr = max(sec["sh_addr"] + sec["sh_size"] for sec in alloc_sections)
    total = (end_vaddr - base_vaddr + 3) & ~3
    buf = bytearray(total)
    for sec in alloc_sections:
        if sec["sh_addr"] < base_vaddr:
            raise ValueError(f"section {sec.name} below 0x{base_vaddr:x}")
        off = sec["sh_addr"] - base_vaddr
        buf[off : off + sec["sh_size"]] = sec.data()
    return bytes(buf), elf.header["e_entry"] - base_vaddr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, nargs="+", default=[ROOT / "rtos_probe.S"])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--display", action="store_true", help="enable the display takeover handoff")
    parser.add_argument("--c", action="store_true", help="link with crt0.S, zvrt_runtime.c, and rtos_c.ld")
    parser.add_argument(
        "--bayer-fixture",
        type=Path,
        default=None,
        help="embed a ZVBR Bayer fixture binary into .rodata.bayer_fixture",
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    elf_path = args.out / "rtos.elf"
    use_c = args.c or any(src.suffix.lower() == ".c" for src in args.source)
    if use_c:
        sources = [str(ROOT / "crt0.S"), str(ROOT / "zvrt_runtime.c"), *(str(s) for s in args.source)]
        if args.bayer_fixture is not None:
            fixture_path = args.bayer_fixture.resolve()
            if not fixture_path.is_file():
                raise FileNotFoundError(f"Bayer fixture not found: {fixture_path}")
            fixture_asm = args.out / "bayer_fixture.S"
            fixture_asm.write_text(
                ".section .rodata.bayer_fixture,\"a\"\n"
                ".balign 4\n"
                ".global zvrt_bayer_fixture_start\n"
                ".global zvrt_bayer_fixture_end\n"
                "zvrt_bayer_fixture_start:\n"
                f".incbin \"{fixture_path.as_posix()}\"\n"
                "zvrt_bayer_fixture_end:\n"
                ".section .note.GNU-stack,\"\",%progbits\n",
                encoding="utf-8",
            )
            sources.append(str(fixture_asm))
        ld_script = ROOT / "rtos_c.ld"
        extra_flags = ["-O2", "-Wall", "-Wextra"]
    else:
        sources = [str(s) for s in args.source]
        ld_script = ROOT / "os.ld"
        extra_flags = []
    subprocess.run(
        [
            str(TOOLS / "arm-none-eabi-gcc.exe"), "-mcpu=cortex-a5", "-marm",
            *extra_flags, "-nostdlib", "-ffreestanding", "-Wl,--build-id=none",
            "-I", str(ROOT), "-T", str(ld_script),
            *sources, "-o", str(elf_path),
        ],
        check=True,
    )
    with elf_path.open("rb") as file:
        elf = ELFFile(file)
        if use_c:
            code, entry = extract_c_image(elf)
        else:
            section = elf.get_section_by_name(".text")
            if section["sh_addr"] != 0:
                raise ValueError("image must be position independent and linked at zero")
            for other in elf.iter_sections():
                if other.name != ".text" and other["sh_flags"] & 2 and other["sh_size"]:
                    raise ValueError(f"unsupported allocated section {other.name}")
                if other["sh_type"] in ("SHT_REL", "SHT_RELA"):
                    raise ValueError("image has relocations")
            code, entry = section.data(), elf.header["e_entry"]
        image = package_image(code, entry, display=args.display)
    output = args.out / "rtos.bin"
    output.write_bytes(image)
    print(f"{output} ({len(image)} bytes)")


if __name__ == "__main__":
    main()
