"""Generate bayer_sensor_tables.h from native av-cam.bin + Backup.bin Unicorn replays."""
import argparse
import json
import struct
import sys
from pathlib import Path

from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_MODE_THUMB, Uc
from unicorn.arm_const import (
    UC_ARM_REG_C1_C0_2,
    UC_ARM_REG_CPSR,
    UC_ARM_REG_FPEXC,
    UC_ARM_REG_LR,
    UC_ARM_REG_PC,
    UC_ARM_REG_R0,
    UC_ARM_REG_R1,
    UC_ARM_REG_R2,
    UC_ARM_REG_R3,
    UC_ARM_REG_SP,
)

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "research/device/zve10_hardware_map"))
sys.path.insert(
    0,
    str(
        REPO
        / "research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030"
    ),
)

from pmca.backup import BackupFile
from extract_imager_profile import recover as recover_imager
from rtos import word
from rtos_harness import Harness, MEM, STACK, STOP

BASE = 0x635C6000
FIRMWARE = REPO / ".local/dumps/av-cam.bin"
BACKUP = REPO / ".local/dumps/staged/audit/Backup.bin"
NATIVE_PARAMS = (
    REPO
    / "research/firmware/zve10-session-2026-11/movie-bayer-audit/movie-native-param-results.json"
)
OUT_HEADER = Path(__file__).resolve().parent / "bayer_sensor_tables.h"


def extract_power_on():
    img = FIRMWARE.read_bytes()
    with BACKUP.open("rb") as f:
        prop = BackupFile(f).getProperty(0xBC0014).data

    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    cpu.mem_map(BASE, (len(img) + 4095) & ~4095)
    cpu.mem_write(BASE, img)
    scratch, stop = 0x20000000, 0x20008000
    cpu.mem_map(scratch, 0x10000)
    for base, size in ((0xF2000000, 0x1000000), (0xF3000000, 0x1000000), (0xFC000000, 0x400000)):
        cpu.mem_map(base, size)

    ops = []

    def on_write(_uc, _acc, addr, _sz, val, _ud):
        ops.append((addr, val))

    def on_host(uc, addr, _sz, _ud):
        r1 = uc.reg_read(UC_ARM_REG_R1)
        r2 = uc.reg_read(UC_ARM_REG_R2)
        if addr == 0x63D29B9C:
            uc.mem_write(r1, prop[:r2])
        elif addr == 0x637AD794:
            ops.append((0, r2))  # addr == 0 encodes delay in microseconds
        uc.reg_write(UC_ARM_REG_R0, 0)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    # Execute IMX284_pmic_acquire/release (0x63D2AC1E / 0x63D2AC7C) natively so SPI ch 0xb
    # SoC clocks/resets (0xf2a300b4/0xf2a30034) are recorded, stubbing only OS locks/semaphores.
    for a in (0x63D29B9C, 0x637AD794, 0x6396F8C4, 0x635DF56C, 0x635DF550, 0x63DCF600, 0x63DCF606):
        cpu.hook_add(UC_HOOK_CODE, on_host, begin=a, end=a)
    cpu.hook_add(UC_HOOK_MEM_WRITE, on_write, begin=0xF0000000, end=0xFFFFFFFF)

    cpu.reg_write(UC_ARM_REG_R0, scratch)
    cpu.reg_write(UC_ARM_REG_SP, scratch + 0xFFF0)
    cpu.reg_write(UC_ARM_REG_LR, stop | 1)
    cpu.emu_start(0x637AD800 | 1, stop, count=200000)
    assert cpu.reg_read(UC_ARM_REG_R0) == 0
    return ops


def extract_imager_mode5():
    report = recover_imager(FIRMWARE, BACKUP, 5, profile_dir=None)
    pre_writes = []
    for w in report["mmio_writes"]:
        addr = int(w["address"], 16)
        val = int(w["value"], 16)
        if 0xFC088300 <= addr <= 0xFC088FFF:
            continue
        pre_writes.append((addr, val))
    uploads = [bytes.fromhex(u["bytes_hex"]) for u in report["uploads"]]
    assert len(uploads) == 3
    return pre_writes, uploads


LIVE_DFE_IDLE_SEED = {
    0xFC020028: 0x000000BB,
    0xFC021000: 0x00000111,
    0xFC021010: 0x00000011,
    0xFC021014: 0x00000111,
    0xFC021024: 0x0005A783,
    0xFC0A0000: 0x00000160,
    0xFC0A1100: 0x00000001,
    0xFC0A1120: 0x03470595,
    0xFC0A3214: 0x00200000,
}


def seed_dfe_idle(harness):
    """Seed RMW CRG/DFE registers with live hardware idle values so bitfield updates preserve existing bits."""
    for addr, val in LIVE_DFE_IDLE_SEED.items():
        harness.put(addr, val)


def make_dfe_harness():
    """Create a Unicorn harness mapped and initialized for native DFE / imager MMIO extraction."""
    harness = Harness()
    for base, size in ((0xFC000000, 0x1000000), (0xF2000000, 0x1000000), (0xF3000000, 0x1000000)):
        harness.u.mem_map(base, size)
    seed_dfe_idle(harness)
    for addr in (0xFC021050, 0xFC021054, 0xFC021058):
        harness.put(addr, 1)
    harness.u.reg_write(UC_ARM_REG_C1_C0_2, 0xF00000)
    harness.u.reg_write(UC_ARM_REG_FPEXC, 0x40000000)

    def do_memset(args):
        harness.u.mem_write(args[0], bytes([args[1] & 0xFF]) * args[2])
        harness.ret(args[0])

    harness.callbacks[0x63AE8AD0] = do_memset
    for fn in (0x63AE1BA4, 0x635DF208, 0x635DF224, 0x6396F8C4, 0x635DF688, 0x635DF684):
        harness.callbacks[fn] = lambda _: harness.ret(0)
    for ctor in (0x6379D44C, 0x6379BF60, 0x637A6D90):
        harness.run(ctor)
    return harness


def extract_dfe_pll_phy():
    harness = make_dfe_harness()
    writes = []
    harness.u.hook_add(
        UC_HOOK_MEM_WRITE,
        lambda _cpu, _acc, addr, _sz, val, _ud: writes.append((addr, val)),
        begin=0xF0000000,
        end=0xFFFFFFFF,
    )
    harness.run(0x63D238B2, 1, 1, 72)
    assert len(writes) == 49, f"Expected 49 writes from 0x63d238b2, got {len(writes)}"
    harness.run(0x63D272D4)
    return writes


def extract_imager_wake(power_ops):
    """Extract IMX284 vtable[38] cold-boot wake: CRG/SLVS-EC writes, 4 serial bursts, and pinmux writes."""
    harness = make_dfe_harness()
    for addr, val in power_ops:
        if addr != 0:
            harness.put(addr, val)

    with BACKUP.open("rb") as f:
        bf = BackupFile(f)

        def make_cb(addr):
            def cb(args):
                res = 0
                if addr == 0x63D29B9C:
                    harness.u.mem_write(args[1], bf.getProperty(args[0]).data[: args[2]])
                elif addr == 0x635DF7D4:
                    res = len(bf.getProperty(args[0]).data)
                elif addr == 0x635DF9B8:
                    res = int.from_bytes(bf.getProperty(args[0]).data, "little")
                elif addr == 0x635DF80C:
                    harness.u.mem_write(args[1], bf.getProperty(args[0]).data)
                    res = 1
                elif addr == 0x635DF860:
                    for i in range(64):
                        key = harness.word(args[0] + i * 4)
                        if key == 0:
                            break
                        harness.u.mem_write(harness.word(args[1] + i * 4), bf.getProperty(key).data)
                    res = 1
                harness.ret(res)
            return cb

        for addr in (
            0x635DF7D4, 0x635DF9B8, 0x635DF80C, 0x635DF860,
            0x635DF980, 0x635DF56C, 0x635DF550, 0x63DCF600, 0x63DCF606,
            0x635DF194, 0x635DF1B0, 0x635DF1CC, 0x637AD794, 0x63D29B9C,
        ):
            harness.callbacks[addr] = make_cb(addr)

        harness.run(0x63D238B2, 1, 1, 72)
        obj = MEM + 0x4000
        harness.run(0x637ABBE4, obj, 0)
        harness.run(0x637ABBA4, obj)

        wake_pre_writes = []
        wake_post_writes = []
        uploads = []
        capturing = [False]

        def on_write(_uc, _acc, addr, _sz, val, _ud):
            if not capturing[0] or (0xFC088300 <= addr <= 0xFC088FFF):
                return
            if not uploads:
                wake_pre_writes.append((addr, val))
            else:
                wake_post_writes.append((addr, val))

        def on_upload(uc, _addr, _sz, _ud):
            if capturing[0]:
                src = uc.reg_read(UC_ARM_REG_R0)
                cnt = uc.reg_read(UC_ARM_REG_R1)
                uploads.append(bytes(uc.mem_read(src, cnt)))

        harness.u.hook_add(UC_HOOK_MEM_WRITE, on_write, begin=0xF0000000, end=0xFFFFFFFF)
        harness.u.hook_add(UC_HOOK_CODE, on_upload, begin=0x637A8C98, end=0x637A8C98)

        capturing[0] = True
        ret = harness.run(0x637AD310, obj)
        capturing[0] = False
        assert ret == 1, f"Expected 0x637ad310 to return 1, got {ret}"

    assert len(uploads) == 4, f"Expected 4 uploads from 0x637ad310, got {len(uploads)}"
    assert [len(u) for u in uploads] == [37, 37, 25, 169], [len(u) for u in uploads]
    assert uploads[0] == uploads[1]
    return wake_pre_writes, [uploads[0], uploads[2], uploads[3]], wake_post_writes


def native_sgc_clock_parameters():
    # Stop at the clock helper so its arguments come from the original
    # initializer and the IMX284 constructor rather than fixture defaults.
    harness = make_dfe_harness()
    harness.run(0x637ABBE4, MEM, 0)
    for address in (0x6379C8AC, 0x63D238B2, 0x63D272D4, 0x6379AA64,
                    0x6379C538, 0x6379ED04, 0x63D267A4):
        harness.callbacks[address] = lambda _: harness.ret(0)
    u = harness.u
    arguments = []

    def record_clock_call(cpu, _address, _size, _context):
        registers = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)
        arguments.extend(cpu.reg_read(reg) for reg in registers)
        arguments.append(harness.word(cpu.reg_read(UC_ARM_REG_SP)))
        cpu.emu_stop()

    u.hook_add(UC_HOOK_CODE, record_clock_call, begin=0x63D26A42, end=0x63D26A42)
    u.reg_write(UC_ARM_REG_CPSR, 0x10)
    u.reg_write(UC_ARM_REG_SP, STACK)
    u.reg_write(UC_ARM_REG_LR, STOP | 1)
    u.reg_write(UC_ARM_REG_R0, MEM + 0x134)
    u.emu_start(0x6379C994 | 1, STOP, count=15000)
    if len(arguments) != 5:
        raise RuntimeError("Original DFE initializer did not reach the SGC clock call")
    return arguments


def extract_dfe_mode5(resource=0x2F, *, force_zpd=False):
    rows = json.loads(NATIVE_PARAMS.read_text())["rows"]
    native_param = next(bytes.fromhex(row["drv_param_hex"]) for row in rows if row["sensor_mode"] == "0x5")
    return extract_dfe(
        resource,
        0x17,
        native_param,
        (2016, 1996, 1122),
        0x25200000,
        0x00E00000,
        mode5=True,
        force_zpd=force_zpd,
    )


def extract_dfe(resource, drive, native_param, geometry, dma_base, dma_bytes, *, mode5=False, force_zpd=False):
    harness = Harness()
    harness.u.mem_map(0xFC000000, 0x400000)
    seed_dfe_idle(harness)
    harness.u.reg_write(UC_ARM_REG_C1_C0_2, 0xF00000)
    harness.u.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
    for fn in (0x63AE1BA4, 0x635DF208, 0x635DF224, 0x6396F8C4):
        harness.callbacks[fn] = lambda _: harness.ret(0)
    for ctor in (0x6379D44C, 0x6379BF60, 0x637A6D90):
        harness.run(ctor)

    table = word(0x64638120 + 0x4490)
    operation = next(
        obj
        for i in range(27)
        if (obj := harness.word(table + 4 * i)) and harness.word(obj + 4) == resource
    )
    harness.callbacks[0x6379BE60] = lambda _: harness.ret(operation)

    clock_sgc_writes = []
    setup_writes = []
    start_writes = []
    current = clock_sgc_writes
    harness.u.hook_add(
        UC_HOOK_MEM_WRITE,
        lambda _cpu, _acc, addr, _sz, val, _ud: current.append((addr, val)),
        begin=0xFC000000,
        end=0xFC3FFFFF,
    )

    clock_args = native_sgc_clock_parameters()
    sgc_obj, frequency, *_ = clock_args
    harness.run(0x6379ED04)
    harness.run(0x63D267A4, sgc_obj)
    harness.run(0x63D26A42, *clock_args)
    harness.run(0x637A3858, frequency)
    harness.u.mem_write(MEM + 0x1000, native_param)
    harness.u.mem_write(MEM + 0x2000, bytes(0x40))
    harness.put(MEM + 0x2004, 1)
    harness.run(0x6379CE58, MEM + 0x1000, MEM + 0x2000)

    owner = harness.run(0x637A6E88, 0, drive, 0)
    runtime = harness.run(0x637A6C84, drive, 0)

    if resource == 0x2F:
        assert harness.word(operation + 0x20) == 0x00200001
    harness.put(owner + 0x5C, MEM + 0x3000)
    stride, width, height = geometry
    harness.u.mem_write(MEM + 0x3000, struct.pack("<6H", stride, 0, 0, width, height, 0))

    assert harness.run(0x6379AEE4, operation, MEM + 0x3500) == 0
    token = harness.word(MEM + 0x3500)

    current = setup_writes

    harness.u.mem_write(MEM, struct.pack("<4I", drive, owner, runtime, 0))
    assert harness.run(0x6379A510, operation, token, MEM) == 0

    harness.u.mem_write(MEM + 0x1000, native_param)
    request = MEM + 0x2000
    for offset, value in (
        (4, drive),
        (8, dma_base),
        (0x10, 0),
        (0x14, 1),
        (0x18, dma_bytes),
    ):
        harness.put(request + offset, value)
    assert harness.run(0x6379CB68, token, MEM + 0x1000, request, 1, 0) == 0

    current = start_writes
    harness.callbacks[0x6379EB38] = lambda _: harness.ret(0)
    assert harness.run(0x6379AB48, operation, token, MEM + 0x3800) == 0
    if resource == 0x39:
        assert harness.run(0x63D2314E, token, 0, 0) == 0
        if force_zpd:
            harness.u.mem_write(0x6426AE84 + 0x14, b"\x01")
        assert harness.run(0x63D23184, token) == 0

    # Also include the DFE IRQ clear/enable writes observed in verify_fast_w0_route
    irq_writes = [
        (0xFC0A0014, 0x80000),
        (0xFC0A002C, 0x1000),
        (0xFC0A0018, 0x80000),
        (0xFC0A0030, 0x1000),
    ]
    return clock_sgc_writes, setup_writes, (irq_writes if mode5 else []) + start_writes


def extract_stock_still(profile_dir):
    harness = make_dfe_harness()
    harness.run(0x637ABBE4, MEM, 0)
    harness.run(0x63D2B564, harness.word(MEM + 0x284), 0, MEM + 0x134)
    request, param = MEM + 0x1000, MEM + 0x2000
    harness.u.mem_write(request, bytes(0x30))
    harness.put(request, 0x37)
    assert harness.run(0x63D2B012, MEM, 0, request, param) == 0
    native_param = bytes(harness.u.mem_read(param, 0x14C))
    clock, setup, start = extract_dfe(0x39, 0x2B, native_param,
                                      (6048, 6048, 4024), 0x35000000, 0x03000000)
    assert {(0xFC0A1354, 0x05F51024), (0xFC0A13D0, 0x0D200000),
            (0xFC0A1454, 0x05E7100F)} <= set(setup)
    assert not any(0xFC0A9200 <= addr < 0xFC0A9300 for addr, _ in clock + setup + start)

    report = recover_imager(FIRMWARE, BACKUP, 0x37, profile_dir=profile_dir, from_mode=1)
    assert report["readout_result"] == 0
    writes = [(int(w["address"], 16), int(w["value"], 16)) for w in report["mmio_writes"]
              if w["phase"] == "readout" and not 0xFC088300 <= int(w["address"], 16) <= 0xFC088FFF]
    uploads = [bytes.fromhex(u["bytes_hex"]) for u in report["uploads"] if u["phase"] == "readout"]
    assert [len(u) for u in uploads] == [251, 45, 124]
    return clock, setup, start, writes, uploads


def fmt_pairs(name, pairs):
    lines = [f"static const struct bayer_reg_op {name}[] = {{"]
    for addr, val in pairs:
        lines.append(f"    {{ 0x{addr:08x}U, 0x{val:08x}U }},")
    lines.append("};")
    return "\n".join(lines)


def fmt_bytes(name, data):
    lines = [f"static const uint8_t {name}[{len(data)}] = {{"]
    for i in range(0, len(data), 16):
        chunk = ", ".join(f"0x{b:02x}U" for b in data[i : i + 16])
        lines.append(f"    {chunk},")
    lines.append("};")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-dir", type=Path, help="captured body properties for still mode")
    args = parser.parse_args()
    power_ops = extract_power_on()
    dfe_pll_phy = extract_dfe_pll_phy()
    wake_pre, wake_uploads, wake_post = extract_imager_wake(power_ops)
    pre_writes, uploads = extract_imager_mode5()
    dfe_clock_sgc, dfe_setup, dfe_start = extract_dfe_mode5()
    movie_acquire, movie_setup, movie_start = extract_dfe_mode5(0x39, force_zpd=True)
    still_clock, still_setup, still_start, still_pre, still_uploads = extract_stock_still(args.profile_dir)

    # The native movie route acquires SGC3 by enabling DFE bit 3, then
    # programs its private register window. Leave its other engines alone.
    def sgc3_only(writes):
        return [(addr, value) for addr, value in writes if 0xFC0A1400 <= addr < 0xFC0A1500]

    def zpdctl_only(writes):
        return [
            (addr, value)
            for addr, value in writes
            if (0xFC098000 <= addr < 0xFC098010)
            or (0xFC098280 <= addr < 0xFC098300)
            or (0xFC099100 <= addr < 0xFC099200)
            or addr in (0xFC098808, 0xFC098908)
        ]

    assert (0xFC0A0000, 8) in movie_acquire
    assert sgc3_only(movie_start) == [(0xFC0A1410, 1)]
    sgc3_setup = [(0xFC0A0000, 8)] + sgc3_only(movie_acquire + movie_setup)

    assert (0xFC0A0000, 0x10) in movie_acquire
    zpdctl_setup = zpdctl_only(movie_acquire) + [(0xFC0A0000, 0x10)] + zpdctl_only(movie_setup)
    zpdctl_trigger = zpdctl_only(movie_start)
    assert (0xFC098280, 3) in zpdctl_trigger and (0xFC099110, 1) in zpdctl_trigger

    header = "\n\n".join(
        [
            "/* SPDX-License-Identifier: GPL-2.0 */",
            "/* Auto-generated by generate_bayer_init.py from av-cam.bin + Backup.bin. */",
            "#ifndef ZV_BAYER_SENSOR_TABLES_H",
            "#define ZV_BAYER_SENSOR_TABLES_H",
            "#include <stdint.h>",
            "struct bayer_reg_op {\n    uint32_t addr;\n    uint32_t value;\n};",
            "#define BAYER_LIVE_WIDTH         1996U",
            "#define BAYER_LIVE_HEIGHT        1122U",
            "#define BAYER_LIVE_STRIDE_PIXELS 2016U",
            "#define BAYER_LIVE_FRAME_BYTES   (BAYER_LIVE_STRIDE_PIXELS * BAYER_LIVE_HEIGHT * 2U)",
            "#define BAYER_RDCW0_BASE_REG     0xfc0a9220U",
            fmt_pairs("imx284_power_on_ops", power_ops),
            fmt_pairs("dfe_mode5_pll_phy_writes", dfe_pll_phy),
            fmt_pairs("dfe_mode5_clock_sgc_writes", dfe_clock_sgc),
            fmt_pairs("imx284_mode5_pre_writes", pre_writes),
            fmt_pairs("imx284_wake_pre_writes", wake_pre),
            fmt_bytes("imx284_wake_upload_0", wake_uploads[0]),
            fmt_bytes("imx284_wake_upload_1", wake_uploads[1]),
            fmt_bytes("imx284_wake_upload_2", wake_uploads[2]),
            fmt_pairs("imx284_wake_post_writes", wake_post),
            fmt_bytes("imx284_mode5_upload_0", uploads[0]),
            fmt_bytes("imx284_mode5_upload_1", uploads[1]),
            fmt_bytes("imx284_mode5_upload_2", uploads[2]),
            fmt_pairs("dfe_mode5_setup_writes", dfe_setup),
            fmt_pairs("dfe_mode5_start_writes", dfe_start),
            fmt_pairs("dfe_mode5_sgc3_setup", sgc3_setup),
            fmt_pairs("dfe_mode5_sgc3_start", sgc3_only(movie_start)),
            fmt_pairs("dfe_mode5_zpdctl_setup", zpdctl_setup),
            fmt_pairs("dfe_mode5_zpdctl_trigger", zpdctl_trigger),
            fmt_pairs("dfe_still_clock_writes", still_clock),
            fmt_pairs("dfe_still_setup_writes", still_setup),
            fmt_pairs("dfe_still_start_writes", still_start),
            fmt_pairs("imx284_still_pre_writes", still_pre),
            *(fmt_bytes(f"imx284_still_upload_{i}", upload) for i, upload in enumerate(still_uploads)),
            "#endif",
            "",
        ]
    )
    OUT_HEADER.write_text(header, encoding="utf-8")
    print(
        f"Wrote {OUT_HEADER} "
        f"(power={len(power_ops)}, pll_phy={len(dfe_pll_phy)}, clock_sgc={len(dfe_clock_sgc)}, "
        f"wake_pre={len(wake_pre)}, wake_uploads={[len(u) for u in wake_uploads]}, wake_post={len(wake_post)}, "
        f"pre={len(pre_writes)}, uploads={[len(u) for u in uploads]}, "
        f"dfe_setup={len(dfe_setup)}, dfe_start={len(dfe_start)})"
    )


if __name__ == "__main__":
    main()
