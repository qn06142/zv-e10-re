"""Build a Version-screen-only event display; no camera access."""
import argparse
import hashlib
import io
import json
import struct
import subprocess
from pathlib import Path
from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parent
STOCK_SHA = "e6459c22859d8978195baa1ef2e93ad6d5f4fcb3dd89c2c2f02c325b46616090"
MARKER_SHA = "280d1b8f3c5a0682301ddb3da5b0cb5c5fbb7a89a8f49549a7192c9045749ed9"
SEGMENT = 0xa0000
STATE = 0x97b30


def sha(data): return hashlib.sha256(data).hexdigest()


def branch_link(source, target):
    delta = (target & ~1) - (source + 4)
    assert delta % 2 == 0 and -(1 << 24) <= delta < (1 << 24)
    value = delta & ((1 << 25) - 1)
    s, i1, i2 = (value >> 24) & 1, (value >> 23) & 1, (value >> 22) & 1
    j1, j2 = 1 ^ i1 ^ s, 1 ^ i2 ^ s
    return struct.pack("<HH", 0xf000 | (s << 10) | ((value >> 12) & 1023),
                       0xd000 | (j1 << 13) | (j2 << 11) | ((value >> 1) & 2047))


def normalize(data):
    if sha(data) == MARKER_SHA:
        data = bytearray(data)
        data[0x41868:0x4186a] = bytes.fromhex("1ab2")
        data[0x4186e:0x41870] = bytes.fromhex("1b14")
        data = bytes(data)
    if sha(data) != STOCK_SHA:
        raise ValueError("Unsupported GUI library")
    return data


def make_image(original, payload, symbols, state_bytes=16):
    original = normalize(original)
    elf = ELFFile(io.BytesIO(original))
    headers = [list(struct.unpack_from("<8I", original, elf["e_phoff"] + 32 * n))
               for n in range(elf["e_phnum"])]
    assert elf["e_phnum"] == 5 and elf["e_phentsize"] == 32
    assert headers[1] == [1, 0, 0, 0, 0x80064, 0x80064, 5, 0x8000]
    assert headers[2] == [1, 0x80064, 0x88064, 0x88064, 0xf824, 0xfac8, 6, 0x8000]
    assert len(original) < SEGMENT
    headers[2][5] = STATE + state_bytes - headers[2][2]
    headers.append([1, SEGMENT, SEGMENT, SEGMENT, 192 + len(payload),
                    192 + len(payload), 5, 0x8000])
    data = bytearray(original)
    data.extend(bytes(SEGMENT - len(data)))
    data.extend(b"".join(struct.pack("<8I", *h) for h in headers))
    data.extend(payload)
    struct.pack_into("<I", data, 28, SEGMENT)
    struct.pack_into("<H", data, 44, 6)
    # Grow the existing zero-initialized .bss to include our private 16-byte state.
    for index, section in enumerate(elf.iter_sections()):
        if section.name == ".bss":
            newsize = STATE + state_bytes - section["sh_addr"]
            struct.pack_into("<I", data, elf["e_shoff"] + index * 40 + 20, newsize)
    # R_ARM_RELATIVE at the table slot adds the runtime load bias to this addend.
    relocations = list(elf.get_section_by_name(".rel.dyn").iter_relocations())
    assert any(r["r_offset"] == 0x8c7a0 and r["r_info_type"] == 23 for r in relocations)
    assert struct.unpack_from("<I", original, 0x847a0)[0] == 0x3f421
    struct.pack_into("<I", data, 0x847a0, symbols["trigger_hook"])
    data[0x41246:0x4124a] = branch_link(0x41246, symbols["ctor_hook"])
    data[0x41872:0x41876] = branch_link(0x41872, symbols["format_hook"])
    # Retain the original exception index, dynamic table and non-executable stack.
    checked = ELFFile(io.BytesIO(data))
    assert checked["e_phoff"] == SEGMENT and checked["e_phnum"] == 6
    assert list(checked.iter_segments())[4]["p_flags"] == 6
    return bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--gcc", default="C:/msys64/ucrt64/bin/arm-none-eabi-gcc.exe")
    parser.add_argument("--objcopy", default="C:/msys64/ucrt64/bin/arm-none-eabi-objcopy.exe")
    args = parser.parse_args()
    original = normalize(args.input.read_bytes())
    args.out.mkdir(parents=True, exist_ok=True)
    payload_elf = args.out / "keys.elf"
    subprocess.run([args.gcc, "-mcpu=cortex-a5", "-mthumb", "-Os", "-fPIE",
        "-ffreestanding", "-fno-builtin", "-fno-stack-protector", "-fno-unwind-tables",
        "-fno-asynchronous-unwind-tables", "-nostdlib", "-Wl,--build-id=none",
        "-T", str(ROOT / "keys.ld"), str(ROOT / "hooks.S"), str(ROOT / "keys.c"),
        "-o", str(payload_elf)], check=True)
    payload_bin = args.out / "keys.bin"
    subprocess.run([args.objcopy, "-O", "binary", "-j", ".text", str(payload_elf),
                    str(payload_bin)], check=True)
    with payload_elf.open("rb") as stream:
        elf = ELFFile(stream)
        symbols = {s.name: s["st_value"] for s in elf.get_section_by_name(".symtab").iter_symbols()}
        assert elf.get_section_by_name(".text")["sh_addr"] == SEGMENT + 192
        assert not any(s["sh_type"] in ("SHT_REL", "SHT_RELA") for s in elf.iter_sections())
    image = make_image(original, payload_bin.read_bytes(), symbols)
    target = args.out / "viewUnified6.gui-keys.so"
    target.write_bytes(image)
    from verify import verify
    tests = verify(original, image, symbols)
    report = {"status": "offline-original-instruction-verified", "hardware_tested": False,
              "input_sha256": sha(original), "output_sha256": sha(image),
              "output_md5": hashlib.md5(image).hexdigest(), "bytes": len(image),
              "symbols": {n: hex(symbols[n]) for n in ["ctor_hook", "trigger_hook", "format_hook"]},
              "state_va": hex(STATE), "tests": tests,
              "limits": ["External widgets and imported APIs mocked",
                         "Physical button names unresolved", "No sequence or OS handoff"]}
    (args.out / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ["status", "output_sha256", "bytes"]}))


if __name__ == "__main__": main()
