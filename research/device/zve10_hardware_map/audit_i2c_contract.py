"""Offline I2C controller and CLK4 reset contract audit using original i2c.ko instructions.

Executes the identified Sony i2c.ko module in Unicorn without touching camera
hardware or generating executable payloads.
"""
import argparse
import json
import struct
import sys
from pathlib import Path

from unicorn import UC_HOOK_MEM_READ
from unicorn.arm_const import (
    UC_ARM_REG_R0,
    UC_ARM_REG_R1,
    UC_ARM_REG_R2,
    UC_ARM_REG_R3,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_dma_contracts import ArmModuleEmulator


I2C_SHA256 = "37b37633a8cdfd6ce60258d646afc2cf11dc50de67cd71a0b53631584412321e"


def audit(repo):
    ko = repo / ".local/dumps/camera_2025/usr/usr/kmod/i2c.ko"
    emu = ArmModuleEmulator(ko, I2C_SHA256)
    emu.map_mmio(0xF2401000, 0x1000)  # I2C0 (0xf2401000) & I2C1 (0xf2401800)
    emu.map_mmio(0xF2A30000, 0x1000)  # CLK4
    scratch = 0x70000000
    emu.cpu.mem_map(scratch, 0x4000)

    devclk_calls = []
    irq_reqs = []
    tasklet_inits = []
    tasklet_scheds = []
    udelay_calls = []
    backup_reads = []
    osal_regs = []
    threads_created = []

    def on_devclk(cpu):
        devclk_calls.append((
            cpu.reg_read(UC_ARM_REG_R0),
            cpu.reg_read(UC_ARM_REG_R1),
            cpu.reg_read(UC_ARM_REG_R2),
        ))
        cpu.reg_write(UC_ARM_REG_R0, 0)

    def on_req_irq(cpu):
        irq_reqs.append((
            cpu.reg_read(UC_ARM_REG_R0),
            cpu.reg_read(UC_ARM_REG_R1),
            cpu.reg_read(UC_ARM_REG_R2),
        ))
        cpu.reg_write(UC_ARM_REG_R0, 0)

    def on_tasklet_init(cpu):
        tasklet_inits.append((
            cpu.reg_read(UC_ARM_REG_R0),
            cpu.reg_read(UC_ARM_REG_R1),
            cpu.reg_read(UC_ARM_REG_R2),
        ))

    def on_tasklet_sched(cpu):
        tasklet_scheds.append(cpu.reg_read(UC_ARM_REG_R0))

    def on_udelay(cpu):
        udelay_calls.append(cpu.reg_read(UC_ARM_REG_R0))

    def on_backup_nread(cpu):
        unit, dst, sz = (cpu.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
        backup_reads.append((unit, sz))
        emu.cpu.mem_write(dst, b"\x00" * sz)
        cpu.reg_write(UC_ARM_REG_R0, 1)

    def on_osal_reg(cpu):
        ep, cb, ctx, ch = (cpu.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
        osal_regs.append((ep, cb, ctx, ch))
        cpu.reg_write(UC_ARM_REG_R0, 0)

    def on_create_thread(cpu):
        attr = cpu.reg_read(UC_ARM_REG_R0)
        name_ptr, _stack, entry, arg = struct.unpack("<IIII", emu.cpu.mem_read(attr, 16))
        threads_created.append((emu.read_cstr(name_ptr), entry, arg))
        cpu.reg_write(UC_ARM_REG_R0, 0)

    def on_test_and_set_bit(cpu):
        nr, addr = cpu.reg_read(UC_ARM_REG_R0), cpu.reg_read(UC_ARM_REG_R1)
        val = struct.unpack("<I", emu.cpu.mem_read(addr, 4))[0]
        old = (val >> nr) & 1
        emu.cpu.mem_write(addr, struct.pack("<I", val | (1 << nr)))
        cpu.reg_write(UC_ARM_REG_R0, old)

    def on_valloc_fail(cpu):
        cpu.reg_write(UC_ARM_REG_R0, 0xFFFFFFFF)

    emu.set_stub("__udif_devio_devclk", on_devclk)
    emu.set_stub("__udif_request_irq", on_req_irq)
    emu.set_stub("tasklet_init", on_tasklet_init)
    emu.set_stub("__tasklet_schedule", on_tasklet_sched)
    emu.set_stub("__const_udelay", on_udelay)
    emu.set_stub("Backup_nread", on_backup_nread)
    emu.set_stub("osal_reg_sync_msg_queue_cb", on_osal_reg)
    emu.set_stub("osal_create_waitable_thread", on_create_thread)
    emu.set_stub("_test_and_set_bit", on_test_and_set_bit)
    emu.set_stub("osal_valloc_msg_wait", on_valloc_fail)
    for noop in ("wake_up_process", "msleep", "osal_free_msg", "osal_snd_msg", "osal_snd_sync_msg", "osal_snd_sync_direct"):
        emu.set_stub(noop, lambda cpu: cpu.reg_write(UC_ARM_REG_R0, 0))

    # 1. Probe both channels (0 -> 0xf2401000, 1 -> 0xf2401800).
    dev_struct = scratch + 0x100
    chs_array = scratch + 0x200
    probe_data = scratch + 0x400
    emu.cpu.mem_write(dev_struct + 0x14, struct.pack("<I", chs_array))
    for ch, base in ((0, 0xF2401000), (1, 0xF2401800)):
        emu.cpu.mem_write(chs_array + ch * 0x5C + 0x10, struct.pack("<I", base))
        rc = emu.call(emu.symbols["i2cu_probe"], [dev_struct, ch, probe_data])
        assert rc == 0, (ch, rc)

    assert backup_reads == [(0x520000, 1), (0x520000, 1)], backup_reads
    assert [(ep, ch) for ep, _, _, ch in osal_regs] == [(0x00520250, 0), (0x00520607, 1)], osal_regs
    assert [t[0] for t in threads_created] == ["i2c_uipc", "i2c_uipc_ch1"], threads_created
    assert len(devclk_calls) == 2 and all(en == 1 and sel == 0 for _, en, sel in devclk_calls)
    assert [cb for _, cb, _ in irq_reqs] == [emu.symbols["i2c_handler"]] * 2
    assert [fn for _, fn, _ in tasklet_inits] == [emu.symbols["i2c_tasklet"]] * 2

    text_base = emu.sections[".text"][1]
    bss_base = emu.sections[".bss"][1]
    algo0 = bss_base + 0x28
    algo1 = bss_base + 0x28 + 0x94

    # 2. Verify readable register dump mask via .text+0x10a4 (reads 13 halfwords, skips +0x18 and +0x30).
    emu.clear_logs()
    emu.call(text_base + 0x10A4, [algo0, 0x123])
    dump_offsets = [addr - 0xF2401000 for addr, size, _ in emu.mmio_reads if size == 2]
    assert dump_offsets == [0x00, 0x04, 0x08, 0x0C, 0x10, 0x14, 0x1C, 0x20, 0x24, 0x28, 0x2C, 0x34, 0x38], dump_offsets

    # 3. Verify reset helper (.text+0x119c): gated by algo+0x8c == 0 (mode flag), not channel index.
    clk4_seq = [
        (0xF2A30048, 4, 2),
        (0xF2A300B8, 4, 8),
        (0xF2A30044, 4, 2),
        (0xF2A300B4, 4, 8),
    ]
    for algo, base in ((algo0, 0xF2401000), (algo1, 0xF2401800)):
        emu.cpu.mem_write(base + 0x38, struct.pack("<H", 3))
        emu.cpu.mem_write(algo + 0x8C, struct.pack("<I", 0))
        emu.clear_logs()
        emu.call(text_base + 0x119C, [algo])
        assert emu.mmio_writes == [(base + 0x34, 2, 0), (base + 0x20, 2, 1)] + clk4_seq, emu.mmio_writes

        emu.cpu.mem_write(base + 0x38, struct.pack("<H", 3))
        emu.cpu.mem_write(algo + 0x8C, struct.pack("<I", 1))
        emu.clear_logs()
        emu.call(text_base + 0x119C, [algo])
        assert emu.mmio_writes == [(base + 0x34, 2, 0), (base + 0x20, 2, 1)], emu.mmio_writes
    emu.cpu.mem_write(algo0 + 0x8C, struct.pack("<I", 0))

    # 4. Verify busy-poll write (.text+0x1328): immediate write when bit 15 clear; 16 polls + reset on stuck bit 15.
    emu.cpu.mem_write(0xF2401010, struct.pack("<H", 0x0000))
    udelay_calls.clear()
    emu.clear_logs()
    assert emu.call(text_base + 0x1328, [algo0, 0x0009, 0x10]) == 0
    assert emu.mmio_writes == [(0xF2401010, 2, 0x0009)] and udelay_calls == []

    emu.cpu.mem_write(0xF2401010, struct.pack("<H", 0x8000))
    emu.cpu.mem_write(0xF2401038, struct.pack("<H", 3))
    udelay_calls.clear()
    emu.clear_logs()
    rc_busy = emu.call(text_base + 0x1328, [algo0, 0x0009, 0x10])
    assert rc_busy != 0 and udelay_calls == [0xA3D6F8] * 16, (rc_busy, len(udelay_calls))
    assert any(a == 0xF2A300B8 and v == 8 for a, _, v in emu.mmio_writes)

    # 5. Verify command builder (.text+0xd44) + TX/start (.text+0x14c0) for write and 2-step read.
    def setup_single_msg(algo, base, slave_addr, flags, payload_bytes, is_last=1):
        msg_ptr = scratch + 0x800
        buf_ptr = scratch + 0x900
        emu.cpu.mem_write(buf_ptr, payload_bytes)
        emu.cpu.mem_write(msg_ptr, struct.pack("<HHII", slave_addr, flags, len(payload_bytes), buf_ptr))
        emu.cpu.mem_write(algo + 0x28, struct.pack("<III", msg_ptr, 1, 0))
        emu.cpu.mem_write(algo + 0x38, struct.pack("<IIII", 0, 1, 0, is_last))
        emu.cpu.mem_write(algo + 0x48, struct.pack("<HHI", slave_addr, flags, len(payload_bytes)))
        emu.cpu.mem_write(algo + 0x50, struct.pack("<I", buf_ptr))
        emu.cpu.mem_write(base + 0x08, struct.pack("<H", 0))
        emu.cpu.mem_write(base + 0x28, struct.pack("<H", 0))
        emu.cpu.mem_write(base + 0x04, struct.pack("<H", 0))

    cmd_out = scratch + 0xA00
    done_out = scratch + 0xA40

    # 7-bit write to 0x3c: [0xaa, 0x55]
    setup_single_msg(algo0, 0xF2401000, 0x3C, 0, b"\xAA\x55")
    assert emu.call(text_base + 0xD44, [algo0, cmd_out, done_out]) == 0
    cmd_val, fifo_cnt = struct.unpack("<H22xI", emu.cpu.mem_read(cmd_out, 28))
    assert (cmd_val, fifo_cnt) == (0x87, 3)
    emu.clear_logs()
    assert emu.call(text_base + 0x14C0, [algo0, cmd_out]) == 0
    assert emu.mmio_writes == [
        (0xF2401024, 2, 1),
        (0xF240100C, 2, 0x78),
        (0xF240100C, 2, 0xAA),
        (0xF240100C, 2, 0x55),
        (0xF2401008, 2, 2),
        (0xF2401004, 2, 0x87),
    ], emu.mmio_writes

    # 7-bit read from 0x3c, 4 bytes: address phase (0x85) then RX phase (0x8a)
    rx_buf = scratch + 0x980
    emu.cpu.mem_write(rx_buf, b"\x00" * 4)
    setup_single_msg(algo0, 0xF2401000, 0x3C, 1, b"\x00" * 4)
    emu.cpu.mem_write(algo0 + 0x50, struct.pack("<I", rx_buf))
    assert emu.call(text_base + 0xD44, [algo0, cmd_out, done_out]) == 0
    cmd1, cnt1 = struct.unpack("<H22xI", emu.cpu.mem_read(cmd_out, 28))
    assert (cmd1, cnt1) == (0x85, 1)
    emu.clear_logs()
    assert emu.call(text_base + 0x14C0, [algo0, cmd_out]) == 0
    assert emu.mmio_writes == [
        (0xF2401024, 2, 1),
        (0xF240100C, 2, 0x79),
        (0xF2401008, 2, 0),
        (0xF2401004, 2, 0x85),
    ], emu.mmio_writes

    assert emu.call(text_base + 0xD44, [algo0, cmd_out, done_out]) == 0
    cmd2, rx_ptr, cnt2 = struct.unpack("<H18xII", emu.cpu.mem_read(cmd_out, 28))
    assert (cmd2, rx_ptr, cnt2) == (0x8A, rx_buf, 4)
    emu.clear_logs()
    assert emu.call(text_base + 0x14C0, [algo0, cmd_out]) == 0
    assert emu.mmio_writes == [
        (0xF2401024, 2, 1),
        (0xF2401008, 2, 3),
        (0xF2401004, 2, 0x8A),
    ], emu.mmio_writes

    # 6. Verify speed divider values inside i2c_xfer for speed modes 0, 1, 0x10, 0x11.
    # Hook schedule_timeout to simulate completion by clearing active flag algo+0x34.
    def on_sched_timeout(cpu):
        emu.cpu.mem_write(algo0 + 0x34, struct.pack("<I", 0))
        cpu.reg_write(UC_ARM_REG_R0, 1)

    emu.set_stub("schedule_timeout", on_sched_timeout)
    xfer_msg = scratch + 0xB00
    xfer_buf = scratch + 0xB40
    emu.cpu.mem_write(xfer_buf, b"\x55")
    emu.cpu.mem_write(xfer_msg, struct.pack("<HHII", 0x3C, 0, 1, xfer_buf))
    speed_cases = []
    for mode in (0, 1, 0x10, 0x11):
        emu.cpu.mem_write(0xF2401010, struct.pack("<H", 0))
        emu.cpu.mem_write(0xF2401014, struct.pack("<H", 0))
        emu.cpu.mem_write(0xF240101C, struct.pack("<H", 1))
        emu.cpu.mem_write(0xF2401038, struct.pack("<H", 3))
        emu.cpu.mem_write(algo0 + 0x38, struct.pack("<I", 0))
        emu.clear_logs()
        rc = emu.call(emu.symbols["i2c_xfer"], [xfer_msg, 1, mode, 0])
        assert rc == 1, (hex(mode), rc)
        w10 = [v for a, _, v in emu.mmio_writes if a == 0xF2401010]
        w14 = [v for a, _, v in emu.mmio_writes if a == 0xF2401014]
        assert len(w10) == 1 and len(w14) == 1
        gate_val = struct.unpack("<I", emu.cpu.mem_read(algo0 + 0x8C, 4))[0]
        clk4_hit = any(a == 0xF2A300B8 and v == 8 for a, _, v in emu.mmio_writes)
        assert gate_val == (0 if mode in (0x10, 0x11) else 1)
        assert clk4_hit == (mode in (0x10, 0x11))
        speed_cases.append({
            "mode": hex(mode),
            "reg_0x10": hex(w10[0]),
            "reg_0x14": hex(w14[0]),
            "algo_0x8c_flag": gate_val,
            "clk4_reset_triggered": clk4_hit,
        })
    assert [(c["reg_0x10"], c["reg_0x14"]) for c in speed_cases] == [
        ("0x35", "0x35"), ("0x9", "0x7"), ("0x9", "0x7"), ("0x35", "0x35")
    ], speed_cases

    # 7. Verify i2c_handler (+0x28 IRQ pending check/ack) and i2c_tasklet (NACK W1C retry & RX FIFO read).
    intr_obj = scratch + 0xC00
    emu.cpu.mem_write(intr_obj + 0x4, struct.pack("<I", algo0))
    emu.cpu.mem_write(algo0 + 0x2C, struct.pack("<II", 1, 0))
    emu.cpu.mem_write(algo0 + 0x90, struct.pack("<I", 0))

    emu.cpu.mem_write(0xF2401028, struct.pack("<H", 0))
    tasklet_scheds.clear()
    emu.clear_logs()
    emu.call(emu.symbols["i2c_handler"], [intr_obj])
    assert emu.mmio_writes == [] and tasklet_scheds == []

    emu.cpu.mem_write(0xF2401028, struct.pack("<H", 1))
    tasklet_scheds.clear()
    emu.clear_logs()
    emu.call(emu.symbols["i2c_handler"], [intr_obj])
    assert emu.mmio_writes == [(0xF2401028, 2, 1)] and len(tasklet_scheds) == 1

    # Tasklet Case A: NACK bit 0x20 set in +0x00, retry counter 3 -> decrements to 2, W1C +0x00=0x20, rewrites +0x04.
    emu.cpu.mem_write(0xF2401000, struct.pack("<H", 0x0020))
    emu.cpu.mem_write(0xF2401028, struct.pack("<H", 0))
    emu.cpu.mem_write(algo0 + 0x24, struct.pack("<I", 3))
    emu.cpu.mem_write(algo0 + 0x58, struct.pack("<H", 0x0087))
    emu.clear_logs()
    emu.call(emu.symbols["i2c_tasklet"], [algo0])
    assert emu.mmio_writes == [(0xF2401000, 2, 0x0020), (0xF2401004, 2, 0x0087)], emu.mmio_writes
    assert struct.unpack("<I", emu.cpu.mem_read(algo0 + 0x24, 4))[0] == 2

    # Tasklet Case B: RX success (+0x00=0, +0x08=0x30 -> 4 bytes in FIFO, +0x0c reads into rx_buf).
    emu.cpu.mem_write(0xF2401000, struct.pack("<H", 0))
    emu.cpu.mem_write(0xF2401008, struct.pack("<H", 0x0030))
    emu.cpu.mem_write(rx_buf, b"\x00" * 4)
    emu.cpu.mem_write(algo0 + 0x58, struct.pack("<H", 0x008A))
    emu.cpu.mem_write(algo0 + 0x6C, struct.pack("<II", rx_buf, 4))
    emu.cpu.mem_write(algo0 + 0x30, struct.pack("<II", 1, 1))
    emu.cpu.mem_write(algo0 + 0x3C, struct.pack("<I", 0))
    emu.cpu.mem_write(algo0 + 0x40, struct.pack("<III", 4, 0, 4))
    # Provide sequential bytes from 0xf240100c right before each 16-bit read.
    rx_seq = iter([0x11, 0x22, 0x33, 0x44])

    def on_rx_read(cpu, access, address, size, value, _):
        if address == 0xF240100C and size == 2:
            nxt = next(rx_seq, None)
            if nxt is not None:
                cpu.mem_write(0xF240100C, struct.pack("<H", nxt))

    rx_hook = emu.cpu.hook_add(UC_HOOK_MEM_READ, on_rx_read)
    emu.call(emu.symbols["i2c_tasklet"], [algo0])
    emu.cpu.hook_del(rx_hook)
    assert bytes(emu.cpu.mem_read(rx_buf, 4)) == b"\x11\x22\x33\x44"

    return {
        "schema_version": 1,
        "status": "offline-original-instruction-i2c-contract-verified",
        "module": ".local/dumps/camera_2025/usr/usr/kmod/i2c.ko",
        "sha256": emu.sha256,
        "current_body_module_identity_checked": False,
        "camera_access_performed": False,
        "read_or_write_permission": False,
        "channels": {
            "0": {"mmio_base": "0xf2401000", "size": "0x800", "uipc_endpoint": "0x00520250", "thread_name": "i2c_uipc"},
            "1": {"mmio_base": "0xf2401800", "size": "0x800", "uipc_endpoint": "0x00520607", "thread_name": "i2c_uipc_ch1"},
        },
        "backup_property_queried": "0x520000",
        "register_offsets_16bit": [hex(x) for x in dump_offsets],
        "busy_poll_mask": "0x8000",
        "busy_poll_max_iterations": 16,
        "busy_poll_udelay_raw_arg": "0xa3d6f8",
        "clk4_reset_sequence": [
            {"address": "0xf2a30048", "value": "0x2", "role": "CLKRST4(IPCLKEN2)+CLR I2C0 HCLK gate"},
            {"address": "0xf2a300b8", "value": "0x8", "role": "CLKRST4(11)+CLR assert reset"},
            {"address": "0xf2a30044", "value": "0x2", "role": "CLKRST4(IPCLKEN2)+SET I2C0 HCLK gate"},
            {"address": "0xf2a300b4", "value": "0x8", "role": "CLKRST4(11)+SET deassert reset"},
        ],
        "clk4_reset_gate": {
            "struct_offset_in_algo": "0x8c",
            "executes_clk4_when_zero": True,
            "zero_in_speed_modes": ["0x10", "0x11"],
            "nonzero_in_speed_modes": ["0x0", "0x1"],
            "checks_channel_index": False,
            "note": "Uses fixed CLK4 bit masks matching I2C0 HCLK (bit 1 at 0xf2a30044/48) and CLKRST4(11) bit 3 (0xf2a300b4/b8) whenever algo+0x8c==0, regardless of channel index at algo+0x88.",
        },
        "command_bits_offset_0x04": {
            "0x80": "GO / trigger transfer",
            "0x08": "RX phase",
            "0x04": "TX phase",
            "0x02": "STOP condition",
            "0x01": "START / repeated-START condition",
        },
        "fifo_chunk_max_bytes": 16,
        "speed_divider_modes": speed_cases,
        "nack_status_w1c_bit_0x00": "0x20",
        "nack_max_retries_from_xfer": 3,
        "limits": [
            "Verified against saved camera_2025 i2c.ko in Unicorn; live-body module identity remains unchecked",
            "Slave addresses, pin mux, pull-ups, and sensor/accessory wiring are not established by driver analysis alone",
            "CLK4 register 0xf2a300b4/b8 offset 0xb0..0xb8 comes from i2c.ko literals; CLK4 bit semantics remain driver-derived",
        ],
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    result = audit(args.repo)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "registers_16bit": len(result["register_offsets_16bit"]),
        "clk4_reset_steps": len(result["clk4_reset_sequence"]),
        "speed_modes": len(result["speed_divider_modes"]),
        "camera_access_performed": False,
    }))
