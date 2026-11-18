"""Build and verify the Sony ZV-E10 2.03 SuperSpeed UVC candidate."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R2, UC_ARM_REG_R4
from unicorn.arm_const import UC_ARM_REG_R7

START = 0xCD6C
END = 0xCD8A
STOCK_SPEED_BLOCK = bytes.fromhex(
    "022803d8012805d0022801d0052302e0032300e0022387f8673007f16702"
)
SPEED_ASSEMBLY = """
.syntax unified
.cpu cortex-a5
.thumb
.text
    @ r0: local speed. r4: CUsbSvc. r7: local frame pointer.
    @ 0 and values above 2 already select 5 in the stock code.
    movs r3, #5
    subs r0, #1
    it eq
    moveq r3, #2
    cmp r0, #1
    bne store
    @ Raise the speed limit for the PAL/NTSC streaming DIDs only.
    ldr.w r0, [r4, #0x9c]
    subs r0, #60
    cmp r0, #1
    it hi
    movhi r3, #3
store:
    add.w r2, r7, #0x67
    strb r3, [r2]
"""


def read_input(path, expected_md5):
    data = path.read_bytes()
    if hashlib.md5(data).hexdigest() != expected_md5:
        raise ValueError(f"Unexpected input build: {path}")
    return data


def speed_block():
    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        source, obj, binary = (temp / name for name in ("speed.S", "speed.o", "speed.bin"))
        source.write_text(SPEED_ASSEMBLY, encoding="ascii")
        subprocess.run(["arm-none-eabi-as", "-o", str(obj), str(source)], check=True)
        subprocess.run(
            ["arm-none-eabi-objcopy", "-j", ".text", "-O", "binary", str(obj), str(binary)],
            check=True,
        )
        return binary.read_bytes()


def run_speed_block(block, local_speed, did):
    machine = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    machine.mem_map(0xC000, 0x1000)
    machine.mem_map(0x10000, 0x2000)
    machine.mem_write(START, block)
    machine.mem_write(0x1009C, struct.pack("<I", did))
    machine.reg_write(UC_ARM_REG_R0, local_speed)
    machine.reg_write(UC_ARM_REG_R4, 0x10000)
    machine.reg_write(UC_ARM_REG_R7, 0x11000)
    machine.emu_start(START | 1, END, count=40)
    buffer = machine.reg_read(UC_ARM_REG_R2)
    if buffer != 0x11067:
        raise ValueError("Unexpected controller ioctl argument pointer")
    return machine.mem_read(buffer, 1)[0]


def build_common(stock):
    replacement = speed_block()
    if stock[START:END] != STOCK_SPEED_BLOCK or len(replacement) != END - START:
        raise ValueError("Controller-speed instruction anchor or patch size mismatch")
    cases = 0
    for local_speed in (0, 1, 2, 3, 4, 0xFFFFFFFF):
        for did in (*range(62), 100, 0xFFFFFFFF):
            original_speed = run_speed_block(STOCK_SPEED_BLOCK, local_speed, did)
            target_speed = 5 if local_speed == 2 and did in (60, 61) else original_speed
            if run_speed_block(replacement, local_speed, did) != target_speed:
                raise ValueError(f"Wrong controller speed for local speed {local_speed}, DID {did}")
            cases += 1
    return stock[:START] + replacement + stock[END:], cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--common", type=Path, required=True, help="Stock libInfraUsbCmn.so")
    parser.add_argument("--video", type=Path, required=True, help="yc42_chunk camera readback")
    parser.add_argument("--yuy2", type=Path, required=True, help="Rebuilt HD producer without runtime speed edits")
    parser.add_argument("--streaming", type=Path, required=True, help="Patched libInfraStreamingUsb.so")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    stock_common = read_input(args.common, "31308976206a837f6f5c571992d2b499")
    common, cases = build_common(stock_common)
    video = read_input(args.video, "702b82f347b6fc25e8d46ddba1836743")
    yuy2 = read_input(args.yuy2, "fec062e0e4f5641235a5b8aa42ba1452")
    streaming = read_input(args.streaming, "4c5deb4a89474c0a3b65356f034a5d9e")
    files = {
        "libInfraUsbCmn.so": common,
        "usbg_video.ko": video,
        "yuy2_1080_v43chunk.so": yuy2,
        "libInfraStreamingUsb.so": streaming,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (args.output / name).write_bytes(data)
    report = {
        "firmware": "Sony ZV-E10 2.03",
        "controller_speed_arm_cases_passed": cases,
        "common_patch_file_offset": hex(START),
        "common_patch_size_bytes": END - START,
        "hardware_tested": False,
        "files": {
            name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in files.items()
        },
    }
    (args.output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{cases} ARM/Thumb controller-speed cases passed")


if __name__ == "__main__":
    main()
