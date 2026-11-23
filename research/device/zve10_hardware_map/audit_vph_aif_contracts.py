"""Offline VPH and AIF display hardware contract audit using original av-cam.bin instructions.

Executes verified Thumb-2 routines from .local/dumps/av-cam.bin (load base 0x635c6000)
in Unicorn without connecting to hardware or claiming device reset/semantic values.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from unicorn import (
    UC_ARCH_ARM,
    UC_HOOK_CODE,
    UC_HOOK_MEM_READ,
    UC_HOOK_MEM_WRITE,
    UC_MODE_THUMB,
    Uc,
)
from unicorn.arm_const import (
    UC_ARM_REG_CPSR,
    UC_ARM_REG_LR,
    UC_ARM_REG_PC,
    UC_ARM_REG_R0,
    UC_ARM_REG_R1,
    UC_ARM_REG_R2,
    UC_ARM_REG_R3,
    UC_ARM_REG_R4,
    UC_ARM_REG_R5,
    UC_ARM_REG_R6,
    UC_ARM_REG_R7,
    UC_ARM_REG_R8,
    UC_ARM_REG_SB,
    UC_ARM_REG_SL,
    UC_ARM_REG_SP,
)

AVCAM_BASE = 0x635C6000
AVCAM_MD5 = "cdcae9d4fdbf66a33704a4c7564e346d"
AVCAM_SHA256 = "bc6cba98c1ce5ef9c7692b9701ed855c25958d285a646ef90dc3fdf398f5c4fa"

STACK_BASE = 0x02000000
STACK_SIZE = 0x10000
SCRATCH_BASE = 0x02100000
SCRATCH_SIZE = 0x20000
STOP_ADDR = 0x02200000

GOT_BASE_OFF = 0x1072120
TRACE_PTR_OFF = GOT_BASE_OFF + 0x8880  # VA 0x646409a0
AIF_TBL_PTR_OFF = GOT_BASE_OFF + 0x9120  # VA 0x64641240 -> 0x63e89724

MMIO_WINDOWS = (
    (0xF3440000, 0x10000),
    (0xF3514000, 0x2000),
    (0xF3800000, 0x10000),
    (0xF3911000, 0x2000),
)


class AvCamEmulator:
    """Unicorn Thumb-2 harness over the local reference av-cam.bin image."""

    def __init__(self, image_bytes):
        self.raw = image_bytes
        self.cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        # Map av-cam.bin through BSS end (32 MiB from AVCAM_BASE).
        self.cpu.mem_map(AVCAM_BASE, 0x02000000)
        self.cpu.mem_write(AVCAM_BASE, image_bytes)
        self.cpu.mem_map(STACK_BASE, STACK_SIZE)
        self.cpu.mem_map(SCRATCH_BASE, SCRATCH_SIZE)
        self.cpu.mem_map(STOP_ADDR, 0x1000)
        for base, size in MMIO_WINDOWS:
            self.cpu.mem_map(base, size)

        # Initialize write-trace mirror pointer so 0x41bf98..0x41c3a4 trace stores land in scratch RAM.
        self.trace_slot = SCRATCH_BASE + 0x1F000
        self.cpu.mem_write(AVCAM_BASE + TRACE_PTR_OFF, struct.pack("<I", self.trace_slot))

        self.mmio_reads = []
        self.mmio_writes = []
        self.stubs = {}
        self.calls = []
        self.cpu.hook_add(UC_HOOK_MEM_READ, self._on_read)
        self.cpu.hook_add(UC_HOOK_MEM_WRITE, self._on_write)
        self.cpu.hook_add(UC_HOOK_CODE, self._on_code)

    def _is_mmio(self, addr):
        return 0xF0000000 <= addr < 0xFF000000

    def _on_read(self, cpu, access, addr, size, value, user_data):
        if self._is_mmio(addr):
            pc = cpu.reg_read(UC_ARM_REG_PC)
            cur = int.from_bytes(cpu.mem_read(addr, size), "little")
            self.mmio_reads.append(
                {
                    "address": f"0x{addr:08x}",
                    "size": size,
                    "value": f"0x{cur:08x}",
                    "pc_file_offset": f"0x{pc - AVCAM_BASE:x}",
                }
            )

    def _on_write(self, cpu, access, addr, size, value, user_data):
        if self._is_mmio(addr):
            pc = cpu.reg_read(UC_ARM_REG_PC)
            self.mmio_writes.append(
                {
                    "address": f"0x{addr:08x}",
                    "size": size,
                    "value": f"0x{value:08x}",
                    "pc_file_offset": f"0x{pc - AVCAM_BASE:x}",
                }
            )

    def _on_code(self, cpu, address, size, user_data):
        off = address - AVCAM_BASE
        if off in self.stubs:
            ret = self.stubs[off](cpu, off)
            if ret is not None:
                cpu.reg_write(UC_ARM_REG_R0, ret & 0xFFFFFFFF)
            lr = cpu.reg_read(UC_ARM_REG_LR)
            cpu.reg_write(UC_ARM_REG_PC, lr)

    def reset_logs(self):
        self.mmio_reads.clear()
        self.mmio_writes.clear()
        self.calls.clear()

    def write_mmio32(self, addr, value):
        self.cpu.mem_write(addr, struct.pack("<I", value))

    def read_mmio32(self, addr):
        return struct.unpack("<I", self.cpu.mem_read(addr, 4))[0]

    def call_thumb(self, file_offset, r0=0, r1=0, r2=0, r3=0, stack_args=(), regs=None, stop_at=None, max_insns=200000):
        sp = STACK_BASE + STACK_SIZE - 0x400
        if stack_args:
            sp -= len(stack_args) * 4
            for i, v in enumerate(stack_args):
                self.cpu.mem_write(sp + i * 4, struct.pack("<I", v & 0xFFFFFFFF))
        self.cpu.reg_write(UC_ARM_REG_SP, sp)
        self.cpu.reg_write(UC_ARM_REG_LR, STOP_ADDR | 1)
        self.cpu.reg_write(UC_ARM_REG_R0, r0 & 0xFFFFFFFF)
        self.cpu.reg_write(UC_ARM_REG_R1, r1 & 0xFFFFFFFF)
        self.cpu.reg_write(UC_ARM_REG_R2, r2 & 0xFFFFFFFF)
        self.cpu.reg_write(UC_ARM_REG_R3, r3 & 0xFFFFFFFF)
        if regs:
            reg_map = {
                "r4": UC_ARM_REG_R4,
                "r5": UC_ARM_REG_R5,
                "r6": UC_ARM_REG_R6,
                "r7": UC_ARM_REG_R7,
                "r8": UC_ARM_REG_R8,
                "sb": UC_ARM_REG_SB,
                "sl": UC_ARM_REG_SL,
            }
            for k, v in regs.items():
                self.cpu.reg_write(reg_map[k], v & 0xFFFFFFFF)
        end = (AVCAM_BASE + stop_at) if stop_at is not None else STOP_ADDR
        self.cpu.emu_start((AVCAM_BASE + file_offset) | 1, end, count=max_insns)
        return self.cpu.reg_read(UC_ARM_REG_R0)


def extract_aif_table(raw):
    ptr_va = struct.unpack_from("<I", raw, AIF_TBL_PTR_OFF)[0]
    tbl_off = ptr_va - AVCAM_BASE
    assert tbl_off == 0x8C3724, hex(tbl_off)
    role_names = {
        0x37: "ext_yuv_ch_a_0xf3911300",
        0x38: "ext_yuv_ch_b_0xf3911280",
        0x39: "vph_yuv1_plane0",
        0x3A: "vph_yuv0_plane0",
        0x3B: "vph_osd0",
        0x3C: "vph_osd1",
        0x3D: "vph_aux0",
        0x3E: "vph_yuv1_plane1",
        0x3F: "vph_yuv0_plane1",
        0x40: "vph_aux1",
        0x41: "ext_0xf3800200",
        0x42: "ext_0xf3800280",
    }
    entries = {}
    for ch in range(0x37, 0x43):
        top, ch_base, flags = struct.unpack_from("<3I", raw, tbl_off + ch * 12)
        entries[f"0x{ch:02x}"] = {
            "channel_index": ch,
            "table_file_offset": f"0x{tbl_off + ch * 12:x}",
            "top_base": f"0x{top:08x}",
            "channel_base": f"0x{ch_base:08x}",
            "flags": f"0x{flags:08x}",
            "flags_byte8_dest_enable": bool(flags & 0xFF),
            "sub_index_byte9": (flags >> 8) & 0xFF,
            "role": role_names[ch],
        }
    return tbl_off, entries


def audit_aif_core(emu):
    cfg_buf = SCRATCH_BASE + 0x100
    ofs_buf = SCRATCH_BASE + 0x200
    rpt_buf = SCRATCH_BASE + 0x300

    # Test 1: OSD0 (ch 0x3b, flags_byte8 == 0) standard buffer setup, ofs/cnt, repeat, start, stop
    emu.write_mmio32(0xF3441300 + 0x1C, 0x00004000)  # +0x1c bit 14 set selects alignment mask 1
    emu.cpu.mem_write(cfg_buf, struct.pack("<6B2xIII", 2, 1, 1, 1, 5, 1, 0xA8200000, 640 * 480 * 4, 0x12345678))
    emu.reset_logs()
    emu.call_thumb(0x41BF98, r0=0x3B, r1=cfg_buf)
    w_cfg_osd0 = list(emu.mmio_writes)
    assert any(w["address"] == "0xf3441320" and w["value"] == "0xa8200000" for w in w_cfg_osd0), w_cfg_osd0
    assert any(w["address"] == "0xf3441324" and int(w["value"], 0) == 640 * 480 * 4 for w in w_cfg_osd0), w_cfg_osd0
    assert any(w["address"] == "0xf344130c" and w["value"] == "0x00000000" for w in w_cfg_osd0), w_cfg_osd0
    ctrl_osd0 = emu.read_mmio32(0xF3441300)
    assert ctrl_osd0 == 0x0000001C, hex(ctrl_osd0)

    # Test 2: cfg[5] == 3 mode (fill / constant address 0xff000000, sets bits 19:16=cfg[4]) + Aux1 ch 0x40 (flags_byte8 == 1 -> writes +0x0c)
    emu.write_mmio32(0xF3441480 + 0x1C, 0x00004000)
    emu.cpu.mem_write(cfg_buf, struct.pack("<6B2xIII", 1, 0, 1, 1, 7, 3, 0xA8300000, 0x00010000, 0xCAFEBABE))
    emu.reset_logs()
    emu.call_thumb(0x41BF98, r0=0x40, r1=cfg_buf)
    w_cfg_aux1 = list(emu.mmio_writes)
    assert any(w["address"] == "0xf344148c" and w["value"] == "0xcafebabe" for w in w_cfg_aux1), w_cfg_aux1
    assert any(w["address"] == "0xf34414a0" and w["value"] == "0xff000000" for w in w_cfg_aux1), w_cfg_aux1
    ctrl_aux1 = emu.read_mmio32(0xF3441480)
    assert ctrl_aux1 == 0x00070832, hex(ctrl_aux1)

    # Test 3: ofs/cnt (0x41c140) on ch 0x3b
    emu.cpu.mem_write(ofs_buf, struct.pack("<4H3I", 10, 20, 30, 40, 0x100, 0x200, 0x300) + struct.pack("<I", 0x400))
    emu.reset_logs()
    emu.call_thumb(0x41C140, r0=0x3B, r1=ofs_buf)
    w_ofs = list(emu.mmio_writes)
    assert len(w_ofs) == 8

    # Test 4: repeat mode (0x41c18c) on ch 0x3b
    emu.cpu.mem_write(rpt_buf, struct.pack("<2B6x3I", 1, 1, 0xA8200000, 0xA8400000, 0xA8600000))
    emu.reset_logs()
    emu.call_thumb(0x41C18C, r0=0x3B, r1=rpt_buf)
    w_rpt = list(emu.mmio_writes)
    assert emu.read_mmio32(0xF3441350) == 0x00000011, hex(emu.read_mmio32(0xF3441350))
    assert [emu.read_mmio32(0xF3441354 + i * 4) for i in range(3)] == [0xA8200000, 0xA8400000, 0xA8600000]

    # Test 5: start (0x41c1e0) and stop (0x41c210)
    emu.reset_logs()
    emu.call_thumb(0x41C1E0, r0=0x3B)
    w_start = list(emu.mmio_writes)
    assert emu.read_mmio32(0xF3441300) & 1 == 1
    emu.reset_logs()
    emu.call_thumb(0x41C210, r0=0x3B)
    w_stop = list(emu.mmio_writes)
    assert emu.read_mmio32(0xF3441304) & 0x40000000 == 0x40000000

    # Test 6: thunks 0x8064ba / 0x8064fc / 0x806524 across sub-indices
    thunk_writes = {}
    emu.reset_logs()
    for idx in range(1, 8):
        emu.call_thumb(0x8064BA, r0=idx, r1=0x11111111 + idx)
    thunk_writes["0x8064ba_idx1_to_7"] = list(emu.mmio_writes)

    emu.reset_logs()
    for ch in (2, 3):
        emu.call_thumb(0x8064FC, r0=ch, r1=0x1234, r2=0x5678)
        emu.call_thumb(0x806524, r0=ch, r1=1)
    thunk_writes["osd_stride_and_mode_thunks"] = list(emu.mmio_writes)

    checked_repeat_cases = 0
    emu.stubs[0x699E48] = lambda cpu, offset: None
    try:
        for channel, base in ((0x3B, 0xF3441300), (0x3C, 0xF3441380)):
            for mode_flag, mask in ((0, 7), (0x4000, 1)):
                emu.write_mmio32(base + 0x1C, mode_flag)
                for slot in range(3):
                    for low_bits in (0, 1, 2, 4):
                        addresses = [0x28200000, 0x28400000, 0x28600000]
                        addresses[slot] |= low_bits
                        emu.cpu.mem_write(rpt_buf, struct.pack("<2B6x3I", 2, 3, *addresses))
                        emu.reset_logs()
                        result = emu.call_thumb(0x41D904, r0=channel, r1=rpt_buf)
                        assert emu.cpu.reg_read(UC_ARM_REG_PC) == STOP_ADDR
                        rejected = bool(low_bits & mask)
                        assert result == (0xFFFFFFF8 if rejected else 0)
                        expected_reads = [base + 0x1C]
                        expected_writes = []
                        if not rejected:
                            expected_reads.append(base + 0x5C)
                            expected_writes = list(zip(
                                (base + 0x50, base + 0x54, base + 0x58, base + 0x5C),
                                (0x32, *addresses),
                            ))
                        assert [int(read["address"], 16) for read in emu.mmio_reads] == expected_reads
                        assert [(int(w["address"], 16), int(w["value"], 16))
                                for w in emu.mmio_writes] == expected_writes
                        checked_repeat_cases += 1
    finally:
        del emu.stubs[0x699E48]

    return {
        "cfg_osd0_ch3b": {"ctrl_written": f"0x{ctrl_osd0:08x}", "writes": w_cfg_osd0},
        "cfg_aux1_ch40_fillmode": {"ctrl_written": f"0x{ctrl_aux1:08x}", "writes": w_cfg_aux1},
        "ofs_cnt_0x41c140": {"writes": w_ofs},
        "repeat_0x41c18c": {"writes": w_rpt},
        "checked_repeat_0x41d904": {
            "cases": checked_repeat_cases,
            "channels": ["0x3b", "0x3c"],
            "alignment": {"register_offset": "0x1c", "bit": 14,
                          "when_clear_bytes": 8, "when_set_bytes": 2},
            "invalid_address_return": -8,
            "rejected_mmio_writes": 0,
            "accepted_read_offsets": ["0x1c", "0x5c"],
            "accepted_write_offsets": ["0x50", "0x54", "0x58", "0x5c"],
            "buffer_completion_established": False,
        },
        "start_0x41c1e0": {"writes": w_start},
        "stop_0x41c210": {"writes": w_stop},
        "thunk_writes": thunk_writes,
    }


def audit_osd_and_output_paths(emu):
    # 1. Execute VPH ColorBar Output 0 (0x4b3f8c) across modes 0..6 (noting Sony TBB maps 3->hw4 and 4->hw3)
    desc_buf = SCRATCH_BASE + 0x1000
    colorbar_out0_map = {}
    for pat in range(7):
        emu.write_mmio32(0xF3445100, 0x00000000)
        emu.cpu.mem_write(desc_buf, struct.pack("<4I", 0, 1, 0, pat))
        emu.reset_logs()
        emu.call_thumb(0x4B3F8C, r0=desc_buf, stop_at=0x4B4018)
        colorbar_out0_map[str(pat)] = f"0x{emu.read_mmio32(0xF3445100):08x}"
    colorbar_out0 = list(emu.mmio_writes)
    assert colorbar_out0_map["4"] == "0x00000013" and colorbar_out0_map["3"] == "0x00000014", colorbar_out0_map

    # 2. Execute VPH ColorBar Output 1 (0x4b3f20)
    emu.write_mmio32(0xF3446100, 0x00000000)
    emu.write_mmio32(0xF3446104, 0x00000000)
    emu.cpu.mem_write(desc_buf, struct.pack("<4I", 5, 1, 0, 0))
    emu.reset_logs()
    emu.call_thumb(0x4B3F20, r0=5, regs={"r4": desc_buf, "r5": 2}, stop_at=0x4B3F58)
    colorbar_out1 = list(emu.mmio_writes)
    assert emu.read_mmio32(0xF3446100) == 0x00050100, hex(emu.read_mmio32(0xF3446100))
    assert emu.read_mmio32(0xF3446104) == 0x28000000, hex(emu.read_mmio32(0xF3446104))

    # 3. Execute VPH Mute Output 0 prefix (0x4b4b30..0x4b4b40) -> sets 0xf3445108 bits 25/24 + 0xf344510c bit 0!
    emu.write_mmio32(0xF3445108, 0x00808080)
    emu.write_mmio32(0xF344510C, 0x00000000)
    emu.reset_logs()
    emu.call_thumb(0x4B4B30, r0=1, regs={"r4": 1, "r5": 1, "r6": 1}, stop_at=0x4B4B40)
    mute_prefix_writes = list(emu.mmio_writes)
    assert emu.read_mmio32(0xF3445108) == 0x03808080 and emu.read_mmio32(0xF344510C) == 0x00000001

    # 4. Execute top commit/enable pulse path (0x49dfec..0x49e004 -> 0x807190/96/a8/ae)
    emu.write_mmio32(0xF3440000, 0)
    emu.write_mmio32(0xF3440008, 0)
    emu.reset_logs()
    emu.call_thumb(0x807190)  # 0xf3440000 |= 0x001
    emu.call_thumb(0x807196)  # 0xf3440000 |= 0x100
    emu.call_thumb(0x8071A8)  # 0xf3440008 |= 0x001
    emu.call_thumb(0x8071AE)  # 0xf3440008 |= 0x100
    top_latch_writes = list(emu.mmio_writes)
    assert emu.read_mmio32(0xF3440000) == 0x101 and emu.read_mmio32(0xF3440008) == 0x101

    # 5. Execute OSD0/1 mixer & format register setters (0x808366..0x808396 -> 0xf3440144..0x0168)
    mixer_struct = SCRATCH_BASE + 0x1200
    emu.cpu.mem_write(mixer_struct, struct.pack("<2H3BH", 640, 480, 1, 1, 2, 1))
    emu.reset_logs()
    emu.call_thumb(0x808366, r0=1)  # 0xf3440144 bit 1 = 1
    emu.call_thumb(0x80836A, r0=1)  # 0xf3440144 bit 0 = 1
    emu.call_thumb(0x80836E, r0=mixer_struct)
    osd0_mixer_writes = list(emu.mmio_writes)

    # 6. Execute Output 0 blender / CSC format struct (0x806dae -> 0xf3445500..5538, 0x806e4e -> 0xf344553c, 0x806e6e -> 0xf3445540)
    blend_struct = SCRATCH_BASE + 0x1300
    emu.cpu.mem_write(blend_struct, struct.pack("<2H4B5H4B", 640, 480, 1, 1, 0, 1, 0x100, 0x200, 0x300, 0x400, 0x500, 1, 0, 1, 1))
    fmt_bytes = SCRATCH_BASE + 0x1340
    emu.cpu.mem_write(fmt_bytes, struct.pack("<4B", 1, 1, 1, 1))  # osd blend mode / flags
    emu.reset_logs()
    emu.call_thumb(0x806DAE, r0=blend_struct)
    emu.call_thumb(0x806E4E, r0=fmt_bytes)
    emu.call_thumb(0x806E6E, r0=0x40)
    out0_blend_writes = list(emu.mmio_writes)

    # 7. Verify 0x4b5818..0x4b58ee OSD AIF setup across DDR1 (0xa8200000) and DDR0 (0x22000000) addresses
    ddr_cases = {}
    for label, phys_addr in (("ddr1_0xa8200000", 0xA8200000), ("ddr0_0x22000000", 0x22000000)):
        emu.write_mmio32(0xF3441300, 0x00000000)  # busy bit 0 = 0
        emu.write_mmio32(0xF3441300 + 0x1C, 0x00004000)  # bit 14 selects alignment mask 1
        emu.write_mmio32(0xF3441380, 0x00000000)
        emu.write_mmio32(0xF3441380 + 0x1C, 0x00004000)
        emu.cpu.mem_write(desc_buf, struct.pack("<I4HI", phys_addr, 640, 0, 0, 480, 1))
        emu.cpu.mem_write(desc_buf + 0x1C, struct.pack("<I", 0))
        emu.reset_logs()
        sp_base = STACK_BASE + STACK_SIZE - 0x500
        emu.cpu.mem_write(sp_base + 0x0C, struct.pack("<I", phys_addr))
        cfg_r6 = SCRATCH_BASE + 0x1400
        emu.cpu.mem_write(cfg_r6, b"\x00" * 0x20)
        emu.cpu.reg_write(UC_ARM_REG_SP, sp_base)
        emu.cpu.reg_write(UC_ARM_REG_R0, 479)
        emu.cpu.reg_write(UC_ARM_REG_R4, desc_buf)
        emu.cpu.reg_write(UC_ARM_REG_R5, 1)
        emu.cpu.reg_write(UC_ARM_REG_R6, cfg_r6)
        emu.cpu.reg_write(UC_ARM_REG_R7, 640 * 4)
        emu.cpu.reg_write(UC_ARM_REG_R8, 0)
        emu.cpu.reg_write(UC_ARM_REG_SB, phys_addr)
        emu.cpu.reg_write(UC_ARM_REG_SL, 640 * 480 * 4)
        emu.cpu.reg_write(UC_ARM_REG_LR, STOP_ADDR | 1)
        emu.cpu.mem_write(sp_base + 0x10, struct.pack("<7II", 0, 0, 0, 0, 0, 0, 0, STOP_ADDR | 1))
        emu.cpu.emu_start((AVCAM_BASE + 0x4B5818) | 1, STOP_ADDR, count=100000)
        ddr_cases[label] = {
            "0xf3441300_ctrl": f"0x{emu.read_mmio32(0xF3441300):08x}",
            "0xf3441320_startadrs": f"0x{emu.read_mmio32(0xF3441320):08x}",
            "0xf3441324_size": f"0x{emu.read_mmio32(0xF3441324):08x}",
            "0xf344132c_cnt0": f"0x{emu.read_mmio32(0xF344132C):08x}",
            "0xf344134c_rptadrs": f"0x{emu.read_mmio32(0xF344134C):08x}",
            "0xf3441350_rpt_ctrl": f"0x{emu.read_mmio32(0xF3441350):08x}",
            "0xf3441370_mode": f"0x{emu.read_mmio32(0xF3441370):08x}",
            "writes": list(emu.mmio_writes),
        }
    ddr1 = ddr_cases["ddr1_0xa8200000"]
    assert ddr1["0xf3441320_startadrs"] == "0xa8200000", ddr1
    assert ddr1["0xf3441324_size"] == f"0x{640 * 480 * 4:08x}", ddr1
    assert ddr1["0xf344132c_cnt0"] == f"0x{479:08x}", ddr1
    assert ddr1["0xf344134c_rptadrs"] == "0x28200000", ddr1
    assert ddr1["0xf3441350_rpt_ctrl"] == "0x00000000", ddr1
    osd0_repeat_sequence = ddr_cases["ddr1_0xa8200000"]["writes"]

    return {
        "colorbar_output0_0x4b3f8c": {
            "mode_map": colorbar_out0_map,
            "final_0xf3445100": colorbar_out0_map["4"],
            "writes": colorbar_out0,
        },
        "colorbar_output1_0x4b3f20": {
            "final_0xf3446100": f"0x{emu.read_mmio32(0xF3446100):08x}",
            "final_0xf3446104": f"0x{emu.read_mmio32(0xF3446104):08x}",
            "writes": colorbar_out1,
        },
        "mute_output0_prefix_0x4b4b30": {
            "final_0xf3445108": f"0x{emu.read_mmio32(0xF3445108):08x}",
            "final_0xf344510c": f"0x{emu.read_mmio32(0xF344510C):08x}",
            "note": "display-v03 wrote 0xf3445108 bits 25:24+YCbCr via os_display.S, omitting 0xf344510c bit 0 (0x807c36) and VPH commit/update",
            "writes": mute_prefix_writes,
        },
        "top_control_0x807190_to_ae": {
            "final_0xf3440000": f"0x{emu.read_mmio32(0xF3440000):08x}",
            "final_0xf3440008": f"0x{emu.read_mmio32(0xF3440008):08x}",
            "writes": top_latch_writes,
        },
        "osd0_mixer_0xf3440144_to_0168": {"writes": osd0_mixer_writes},
        "output0_blender_0xf3445500_to_5540": {"writes": out0_blend_writes},
        "osd0_repeat_setup_0x4b5818": {
            "ddr1_0xa8200000": ddr_cases["ddr1_0xa8200000"],
            "ddr0_0x22000000": ddr_cases["ddr0_0x22000000"],
            "final_0xf3441320_startadrs": ddr1["0xf3441320_startadrs"],
            "final_0xf3441324_size": ddr1["0xf3441324_size"],
            "final_0xf3441350_rpt_ctrl": ddr1["0xf3441350_rpt_ctrl"],
            "final_0xf3441370_mode": ddr1["0xf3441370_mode"],
        },
    }


def audit_osd_pipeline_and_irqs(emu, raw):
    """Verify RTOS VDF OSD consumer, VPH OSD queue 0x6603c4 fan-out, and IRQ 102/110 callbacks."""
    # 1. VDF::VdfOsdImageSizeProcessor (0x15bfb0, vptr 0xfbbc00) + SubsystemAccessor (vptr 0xfbd3b0)
    proc_obj = SCRATCH_BASE + 0x2000
    sub_obj = SCRATCH_BASE + 0x2100
    pin_info = SCRATCH_BASE + 0x4200
    arg_r1 = SCRATCH_BASE + 0x4300
    emu.cpu.mem_write(proc_obj, b"\x00" * 0x40)
    emu.cpu.mem_write(proc_obj, struct.pack("<I", AVCAM_BASE + 0xFBBC00))

    vdf_events = []
    vdf_stubs = {
        0x72F47C: lambda cpu, _off: (vdf_events.append(("log", f"0x{cpu.reg_read(UC_ARM_REG_R1):08x}")), 0)[1],
        0x15BE88: lambda cpu, _off: (vdf_events.append(("branch", "0x15be88")), 0)[1],
        0x15BF1C: lambda cpu, _off: (vdf_events.append(("branch", "0x15bf1c")), 0)[1],
    }
    emu.stubs.update(vdf_stubs)
    vdf_cases = {}
    try:
        for label, prior_tt, sel, target_w, trans_type, exp_branch, exp_tag, exp_426 in (
            ("trans_type_0", 0xFF, 0, 640, 0, "0x15be88", "0x00004444", 0),
            ("trans_type_1", 0x00, 1, 426, 1, "0x15bf1c", "0x00008888", 1),
        ):
            vdf_events.clear()
            emu.cpu.mem_write(sub_obj, b"\x00" * 0x2000)
            emu.cpu.mem_write(sub_obj, struct.pack("<I", AVCAM_BASE + 0xFBD3B0))
            emu.cpu.mem_write(sub_obj + 0x1A90, struct.pack("<I", prior_tt))
            # PIN_OSD_IMAGE_SIZE_INFO: +0x10 Target_SizeH, +0x12 Target_SizeV, +0x14 Sel, +0x1a Trans_Type
            emu.cpu.mem_write(pin_info, b"\x00" * 0x94)
            emu.cpu.mem_write(pin_info, struct.pack("<II", 1, 0xA8200000))
            emu.cpu.mem_write(pin_info + 0x10, struct.pack("<HHI", target_w, 480, sel))
            emu.cpu.mem_write(pin_info + 0x18, struct.pack("<4B", 3, 0, trans_type, 1))
            emu.cpu.mem_write(arg_r1, b"\x00" * 0x40)

            ret = emu.call_thumb(0x15BFB0, r0=proc_obj, r1=arg_r1, r2=sub_obj, r3=pin_info, stack_args=(0,))
            assert ret == 0, (label, ret)
            log_tag = next(val for kind, val in vdf_events if kind == "log")
            branch_hit = next(val for kind, val in vdf_events if kind == "branch")
            stored_sel = struct.unpack("<I", emu.cpu.mem_read(sub_obj + 0x1A8C, 4))[0]
            stored_tt = struct.unpack("<I", emu.cpu.mem_read(sub_obj + 0x1A90, 4))[0]
            stored_426 = struct.unpack("<B", emu.cpu.mem_read(sub_obj + 0x1A88, 1))[0]
            assert log_tag == exp_tag and branch_hit == exp_branch, (label, vdf_events)
            assert (stored_sel, stored_tt, stored_426) == (sel, trans_type, exp_426), (label, stored_sel, stored_tt, stored_426)
            vdf_cases[label] = {
                "input_sel": sel,
                "input_trans_type": trans_type,
                "input_target_size_h": target_w,
                "logged_format_tag_r1": log_tag,
                "vtable_branch_target": branch_hit,
                "subsys_stored_sel_offset_0x1a8c": stored_sel,
                "subsys_stored_trans_type_offset_0x1a90": stored_tt,
                "subsys_is_426_wide_offset_0x1a88": stored_426,
            }
    finally:
        for k in vdf_stubs:
            emu.stubs.pop(k, None)

    # 2. VPH OSD queue 0x006603c4 (at 0x497550 -> handle 0x6441cdac) and staging fan-out 0x498aa4
    q_ep = struct.unpack_from("<I", raw, 0x497550)[0]
    q_companion = struct.unpack_from("<I", raw, 0x497554)[0]
    assert q_ep == 0x006603C4 and q_companion == 0x006605A9, (hex(q_ep), hex(q_companion))

    staging_va = 0x64419E70
    dst_va = 0x6441AF40
    marker_desc = bytes((0xA0 + i) & 0xFF for i in range(0x38))
    route_fanout = {}
    for route_sel in (0, 1, 2):
        emu.cpu.mem_write(staging_va, b"\x00" * 0x2D0)
        emu.cpu.mem_write(staging_va + 0xFC, b"\x01")
        emu.cpu.mem_write(staging_va + 0x100, marker_desc)
        emu.cpu.mem_write(staging_va + 0x128, struct.pack("<I", route_sel))
        expected_desc = bytes(emu.cpu.mem_read(staging_va + 0x100, 0x38))
        emu.cpu.mem_write(dst_va + 0x338, b"\x00" * 0x78)

        emu.call_thumb(0x498AA4, r0=dst_va)
        r1_flag = emu.cpu.mem_read(dst_va + 0x338, 1)[0]
        r0_flag = emu.cpu.mem_read(dst_va + 0x374, 1)[0]
        r1_match = bytes(emu.cpu.mem_read(dst_va + 0x33C, 0x38)) == expected_desc
        r0_match = bytes(emu.cpu.mem_read(dst_va + 0x378, 0x38)) == expected_desc
        dirty_after = emu.cpu.mem_read(staging_va + 0xFC, 1)[0]
        assert dirty_after == 0, (route_sel, dirty_after)
        expected = {
            0: (0, False, 1, True),
            1: (1, True, 0, False),
            2: (1, True, 1, True),
        }[route_sel]
        assert (r1_flag, r1_match, r0_flag, r0_match) == expected, (route_sel, r1_flag, r1_match, r0_flag, r0_match)
        route_fanout[str(route_sel)] = {
            "route1_osd0_flag_0x338": r1_flag,
            "route1_osd0_desc_0x33c_copied": r1_match,
            "route0_osd1_flag_0x374": r0_flag,
            "route0_osd1_desc_0x378_copied": r0_match,
            "staging_dirty_flag_cleared_0xfc": dirty_after == 0,
        }

    # 3. VPH VSYNC IRQ 102 (0x806294) / IRQ 110 (0x806352), 0xf3440038 mask BFI, and completion callbacks 0x4b59ec / 0x4b5a84
    irq102_va, _, irq102_num = struct.unpack_from("<3I", raw, 0xFCC4D0)
    irq110_va, _, irq110_num = struct.unpack_from("<3I", raw, 0xFCC4E0)
    irq102_off = (irq102_va & ~1) - AVCAM_BASE
    irq110_off = (irq110_va & ~1) - AVCAM_BASE
    assert irq102_num == 102 and irq102_off == 0x806294, (irq102_num, hex(irq102_off))
    assert irq110_num == 110 and irq110_off == 0x806352, (irq110_num, hex(irq110_off))

    # Exercise 0x49b42c -> 0x807230 -> 0x49360c BFI into 0xf3440038 bits 15:0
    emu.cpu.mem_write(AVCAM_BASE + 0xEF317A, struct.pack("<H", 0))
    emu.write_mmio32(0xF3440038, 0xDEAD0000)
    emu.call_thumb(0x49B42C, r0=1, r1=1, r2=9)
    val_after_irq102_bit = emu.read_mmio32(0xF3440038)
    emu.call_thumb(0x49B42C, r0=1, r1=1, r2=10)
    val_after_irq110_bit = emu.read_mmio32(0xF3440038)
    assert val_after_irq102_bit == 0xDEAD0200 and val_after_irq110_bit == 0xDEAD0600, (
        hex(val_after_irq102_bit),
        hex(val_after_irq110_bit),
    )

    cb_off = 0x1FF0000
    cb_va = (AVCAM_BASE + cb_off) | 1
    emu.cpu.mem_write(AVCAM_BASE + cb_off, struct.pack("<HH", 0x4770, 0xBF00))
    cb_calls = []

    def on_synthetic_cb(cpu, _off):
        cb_calls.append(
            (
                cpu.reg_read(UC_ARM_REG_R0),
                cpu.reg_read(UC_ARM_REG_R1),
                cpu.reg_read(UC_ARM_REG_R2),
            )
        )
        return None

    route_stubs = {
        cb_off: on_synthetic_cb,
        0x4B5664: lambda _cpu, _off: 0,
        0x4B56AC: lambda _cpu, _off: 0,
        0x4B5B18: lambda _cpu, _off: 0,
        0x808366: lambda _cpu, _off: 0,
        0x8084A0: lambda _cpu, _off: 0,
        0x7DC0F6: lambda _cpu, _off: 0,
        0x8038F8: lambda _cpu, _off: 0,
        0x4A2580: lambda _cpu, _off: 0,
        0x49FE48: lambda _cpu, _off: 0,
        0x4B0748: lambda _cpu, _off: 0,
        0x49B58C: lambda _cpu, _off: 0,
    }
    emu.stubs.update(route_stubs)
    try:
        desc_cb = SCRATCH_BASE + 0x4400
        # OSD0 / Route 1 latch (0x4b6298) + completion callback (0x4b59ec)
        emu.cpu.mem_write(AVCAM_BASE + 0xF5D196, b"\x00")
        emu.cpu.mem_write(AVCAM_BASE + 0xF5D191, b"\x00")
        emu.cpu.mem_write(AVCAM_BASE + 0xEFB180, b"\x00\x00")
        emu.cpu.mem_write(AVCAM_BASE + 0xE57EEC, struct.pack("<I", 0))
        emu.cpu.mem_write(AVCAM_BASE + 0xE57F58, struct.pack("<I", 0))
        emu.cpu.mem_write(desc_cb, b"\x00" * 0x38)
        emu.cpu.mem_write(desc_cb + 0x2C, struct.pack("<H2xI", 0x1234, cb_va))

        emu.call_thumb(0x4B6298, r0=desc_cb, r1=1, r2=0)
        r1_flag_latched = emu.cpu.mem_read(AVCAM_BASE + 0xF5D191, 1)[0]
        r1_tok_latched = struct.unpack("<H", emu.cpu.mem_read(AVCAM_BASE + 0xEFB180, 2))[0]
        r1_cb_latched = struct.unpack("<I", emu.cpu.mem_read(AVCAM_BASE + 0xE57EEC, 4))[0]
        assert (r1_flag_latched, r1_tok_latched, r1_cb_latched) == (1, 0x1234, cb_va), (
            r1_flag_latched,
            hex(r1_tok_latched),
            hex(r1_cb_latched),
        )

        cb_calls.clear()
        emu.call_thumb(0x4B59EC)
        r1_flag_after = emu.cpu.mem_read(AVCAM_BASE + 0xF5D191, 1)[0]
        assert len(cb_calls) == 1 and cb_calls[0] == (0, 0x1234, 1) and r1_flag_after == 0, (cb_calls, r1_flag_after)
        r1_res = {
            "route_setter": "0x004b6298",
            "completion_handler": "0x004b59ec",
            "latched_flag_offset": "0xf5d191",
            "latched_token_offset": "0xefb180",
            "latched_callback_offset": "0xe57eec",
            "flag_latched": r1_flag_latched,
            "token_latched": f"0x{r1_tok_latched:04x}",
            "callback_status_r0": cb_calls[0][0],
            "callback_token_r1": f"0x{cb_calls[0][1]:04x}",
            "callback_route_r2": cb_calls[0][2],
            "flag_after": r1_flag_after,
        }

        # OSD1 / Route 0 latch (0x4b6340) + completion callback (0x4b5a84)
        emu.cpu.mem_write(AVCAM_BASE + 0xF5D18D, b"\x00")
        emu.cpu.mem_write(AVCAM_BASE + 0xF5D194, b"\x00")
        emu.cpu.mem_write(AVCAM_BASE + 0xEFB15A, b"\x00\x00")
        emu.cpu.mem_write(AVCAM_BASE + 0xE57F88, struct.pack("<I", 0))
        emu.cpu.mem_write(AVCAM_BASE + 0xE57EE4, struct.pack("<I", 0))
        emu.cpu.mem_write(desc_cb + 0x2C, struct.pack("<H2xI", 0x5678, cb_va))

        emu.call_thumb(0x4B6340, r0=desc_cb, r1=1, r2=0)
        r0_flag_latched = emu.cpu.mem_read(AVCAM_BASE + 0xF5D194, 1)[0]
        r0_tok_latched = struct.unpack("<H", emu.cpu.mem_read(AVCAM_BASE + 0xEFB15A, 2))[0]
        r0_cb_latched = struct.unpack("<I", emu.cpu.mem_read(AVCAM_BASE + 0xE57F88, 4))[0]
        assert (r0_flag_latched, r0_tok_latched, r0_cb_latched) == (1, 0x5678, cb_va), (
            r0_flag_latched,
            hex(r0_tok_latched),
            hex(r0_cb_latched),
        )

        cb_calls.clear()
        emu.call_thumb(0x4B5A84)
        r0_flag_after = emu.cpu.mem_read(AVCAM_BASE + 0xF5D194, 1)[0]
        assert len(cb_calls) == 1 and cb_calls[0] == (0, 0x5678, 0) and r0_flag_after == 0, (cb_calls, r0_flag_after)
        r0_res = {
            "route_setter": "0x004b6340",
            "completion_handler": "0x004b5a84",
            "latched_flag_offset": "0xf5d194",
            "latched_token_offset": "0xefb15a",
            "latched_callback_offset": "0xe57f88",
            "flag_latched": r0_flag_latched,
            "token_latched": f"0x{r0_tok_latched:04x}",
            "callback_status_r0": cb_calls[0][0],
            "callback_token_r1": f"0x{cb_calls[0][1]:04x}",
            "callback_route_r2": cb_calls[0][2],
            "flag_after": r0_flag_after,
        }
    finally:
        for k in route_stubs:
            emu.stubs.pop(k, None)

    return {
        "vdf_osd_image_size_processor_0x15bfb0": vdf_cases,
        "vph_osd_queue_and_routes": {
            "queue_endpoint_literal_0x497550": f"0x{q_ep:08x}",
            "queue_companion_literal_0x497554": f"0x{q_companion:08x}",
            "queue_handle_va": "0x6441cdac",
            "staging_buffer_va": f"0x{staging_va:08x}",
            "route_fanout_0x498aa4": route_fanout,
        },
        "vph_vsync_irqs_and_callbacks": {
            "irq_102_table_offset": "0xfcc4d0",
            "irq_102_handler": f"0x{irq102_off:08x}",
            "irq_110_table_offset": "0xfcc4e0",
            "irq_110_handler": f"0x{irq110_off:08x}",
            "mask_bfi_0x49b42c_0xf3440038": {
                "after_bit9_irq102": f"0x{val_after_irq102_bit:08x}",
                "after_bit10_irq110": f"0x{val_after_irq110_bit:08x}",
            },
            "osd0_route1_completion_0x4b59ec": r1_res,
            "osd1_route0_completion_0x4b5a84": r0_res,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    avcam_path = args.repo / ".local/dumps/av-cam.bin"
    raw = avcam_path.read_bytes()
    md5 = hashlib.md5(raw).hexdigest()
    sha256 = hashlib.sha256(raw).hexdigest()
    assert md5 == AVCAM_MD5 and sha256 == AVCAM_SHA256, (md5, sha256)

    tbl_off, aif_table = extract_aif_table(raw)
    emu = AvCamEmulator(raw)
    aif_core = audit_aif_core(emu)
    osd_and_out = audit_osd_and_output_paths(emu)
    osd_pipeline_and_irqs = audit_osd_pipeline_and_irqs(emu, raw)

    # Check output 1 enable setter at 0x495834/0x495848 vs output 0 at 0x4955d8/0x4955e8
    emu.write_mmio32(0xF3440144, 0)
    emu.write_mmio32(0xF3440184, 0)
    emu.reset_logs()
    emu.call_thumb(0x808366, r0=1)
    emu.call_thumb(0x80836A, r0=1)
    emu.call_thumb(0x8084A0, r0=1)
    emu.call_thumb(0x8084A4, r0=1)
    assert emu.read_mmio32(0xF3440144) == 3 and emu.read_mmio32(0xF3440184) == 3

    report = {
        "schema_version": 1,
        "status": "offline-original-instruction-vph-aif-contracts-verified",
        "camera_access_performed": False,
        "read_or_write_permission": False,
        "source_firmware": {
            "path": ".local/dumps/av-cam.bin",
            "bytes": len(raw),
            "load_base": f"0x{AVCAM_BASE:08x}",
            "md5": md5,
            "sha256": sha256,
        },
        "aif_table": {
            "got_pointer_offset": f"0x{AIF_TBL_PTR_OFF:x}",
            "table_file_offset": f"0x{tbl_off:x}",
            "stride_bytes": 12,
            "vph_channels": {k: aif_table[k] for k in ("0x39", "0x3a", "0x3b", "0x3c", "0x3d", "0x3e", "0x3f", "0x40")},
            "all_audited_channels": aif_table,
            "core_functions": {
                "configure": "0x41bf98",
                "offsets_and_counts": "0x41c140",
                "repeat_config": "0x41c18c",
                "start": "0x41c1e0",
                "disable_start_bit": "0x41c26c",
                "stop": "0x41c210",
                "read_busy_bit": "0x41c240",
                "read_stop_bit31": "0x41c2a8",
                "read_idle_bit14": "0x41c3b4",
                "write_trace_pointer_file_offset": f"0x{TRACE_PTR_OFF:x}",
            },
        },
        "vph_osd_and_yuv_sequences": {
            "osd0_and_1_start": "0x4b62dc / 0x4b6340 -> 0x4b5664 -> 0x4b56ac(AIF ch 0x3b/0x3c) -> 0x4b5b18(mixer/blend) -> 0x808366/0x8084a0 -> 0x7dc0f6(0x3b/0x3c)",
            "osd_aif_repeat_struct_path": "0x4b5818 sets rpt[0]=1 on the .bss cfg block at 0xe57f5c (zero-initialized in av-cam.bin), while 0x41d904->0x41c18c receives the zero repeat block and writes 0xf3441350=0x00000000 in this isolated entry test",
            "osd_ddr_window_check": "0x4b5848 tests 0xa0000000..0xafffffff and 0xe0000000..0xefffffff (stores cfg[5]=2 when outside those windows on the alt path), and 0x8064ba masks startadrs to 31 bits in 0xf344134c",
            "yuv_start_thunks": "0x4b929c/0x4b92ae (AIF 0x3a/0x3f YUV0) and 0x4b9aea/0x4b9af8 (AIF 0x39/0x3e YUV1), gated by 0x80534e (-> 0x8084a4 / 0x80836a)",
            "output_banks": {
                "output0_timing_colorbar_mute": "0xf3445000..0xf34456ff",
                "output0_osd_mixer": "0xf3440144..0xf3440168",
                "output0_blend_csc": "0xf3445500..0xf3445540",
                "output1_timing_colorbar_mute": "0xf3446000..0xf34466ff",
                "output1_osd_mixer": "0xf3440184..0xf34401a8",
                "output1_blend_csc": "0xf3446500..0xf3446540",
                "top_control_and_irq": "0xf3440000..0xf34400cc",
            },
        },
        "aif_core_runs": aif_core,
        "vph_output_runs": osd_and_out,
        "osd_pipeline_and_irqs": osd_pipeline_and_irqs,
        "unresolved_hardware_questions": [
            "Whether LCD glass uses VPH Output 0 (0xf3445000 / OSD0 0xf3441300 / 0xf3440144) or Output 1 (0xf3446000 / OSD1 0xf3441380 / 0xf3440184) during active display",
            "Whether 0xf3440000..0xf3440010 bit 0 / bit 8 acts as shadow-register update latch on VSYNC and/or top enable",
            "Whether VPH AIF OSD channels continuously auto-repeat from +0x54..+0x5c without VSYNC ISR intervention or require ISR acknowledgement at 0xf3440048/0xf3440068",
            "Why display-v03 produced no visible LCD change: omitted 0xf344510c bit 0 and top update, possible kernel_restart_prepare clock/routing/AIF shutdown, or wrong output bank",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "vph_aif_channels": len(report["aif_table"]["vph_channels"]),
                "all_aif_table_entries": len(aif_table),
                "colorbar_out0": osd_and_out["colorbar_output0_0x4b3f8c"]["final_0xf3445100"],
                "colorbar_out1": osd_and_out["colorbar_output1_0x4b3f20"]["final_0xf3446100"],
                "osd0_rpt_ctrl": osd_and_out["osd0_repeat_setup_0x4b5818"]["final_0xf3441350_rpt_ctrl"],
                "camera_access_performed": False,
            }
        )
    )


if __name__ == "__main__":
    main()
