"""Offline XDMAC and DMA330 contract audit using original module instructions.

Executes verified local Sony modules (dmac.ko and dma330.ko) in Unicorn
without touching hardware or emitting executable payloads.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile
from unicorn import (
    UC_ARCH_ARM,
    UC_HOOK_CODE,
    UC_HOOK_MEM_READ,
    UC_HOOK_MEM_WRITE,
    UC_MODE_ARM,
    Uc,
)
from unicorn.arm_const import (
    UC_ARM_REG_LR,
    UC_ARM_REG_PC,
    UC_ARM_REG_R0,
    UC_ARM_REG_R1,
    UC_ARM_REG_R2,
    UC_ARM_REG_R3,
    UC_ARM_REG_SP,
)


DMAC_SHA256 = "718284caacf31654151fac234db7293d8338e348687c37b6e3f65dbf24de1522"
DMA330_SHA256 = "a86794fb8ab97fb27adac21bbcb067d424b787f3815d97bf91942b460dffd86d"

MOD_BASE = 0x10000000
STUB_BASE = 0x10800000
STACK_BASE = 0x02000000
STOP_ADDR = 0x02100000
TASK_BASE = 0x02200000


def _align(value, gran=16):
    return (value + gran - 1) & ~(gran - 1)


def _s24(value):
    return (value - 0x1000000) if (value & 0x800000) else value


class ArmModuleEmulator:
    """Minimal ET_REL loader and Unicorn harness for Sony ARM kernel modules."""

    def __init__(self, ko_path, expected_sha256):
        raw = ko_path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expected_sha256:
            raise ValueError(f"Unexpected SHA-256 for {ko_path}: {digest}")
        self.sha256 = digest
        self.cpu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.sections = {}
        self.symbols = {}
        self.stubs = {}
        self.stub_handlers = {}
        self.events = []
        self.mmio_writes = []
        self.mmio_reads = []

        self._load_elf(ko_path)
        self._setup_runtime()
        self._register_default_stubs()

    def _load_elf(self, ko_path):
        with ko_path.open("rb") as f:
            elf = ELFFile(f)
            symtab = elf.get_section_by_name(".symtab")

            cursor = MOD_BASE
            alloc_secs = []
            for idx, sec in enumerate(elf.iter_sections()):
                if sec["sh_flags"] & 2:  # SHF_ALLOC
                    alloc_secs.append((idx, sec, cursor))
                    size = max(sec["sh_size"], 4)
                    self.sections[sec.name] = (idx, cursor, size)
                    cursor = _align(cursor + size, 16)

            map_size = _align(cursor - MOD_BASE + 0x1000, 4096)
            self.cpu.mem_map(MOD_BASE, map_size)
            for _, sec, base in alloc_secs:
                if sec["sh_type"] != "SHT_NOBITS" and sec["sh_size"] > 0:
                    self.cpu.mem_write(base, sec.data())

            sec_by_idx = {idx: (base, sec) for idx, sec, base in alloc_secs}
            undef_names = set()
            for sym in symtab.iter_symbols():
                shndx = sym["st_shndx"]
                if shndx == "SHN_UNDEF":
                    if sym.name:
                        undef_names.add(sym.name)
                elif isinstance(shndx, int) and shndx in sec_by_idx:
                    if sym.name:
                        self.symbols[sym.name] = sec_by_idx[shndx][0] + sym["st_value"]

            # Place external stubs and outer_cache descriptor in STUB_BASE.
            self.cpu.mem_map(STUB_BASE, 0x4000)
            stub_cursor = STUB_BASE
            for name in sorted(undef_names):
                if name == "outer_cache":
                    self.outer_cache_addr = STUB_BASE + 0x2000
                    self.outer_cache_sync_addr = STUB_BASE + 0x2100
                    self.cpu.mem_write(self.outer_cache_sync_addr, struct.pack("<I", 0xE12FFF1E))
                    self.cpu.mem_write(self.outer_cache_addr + 0x1C, struct.pack("<I", self.outer_cache_sync_addr))
                    self.stubs[name] = self.outer_cache_addr
                else:
                    self.cpu.mem_write(stub_cursor, struct.pack("<I", 0xE12FFF1E))
                    self.stubs[name] = stub_cursor
                    stub_cursor += 4

            # Apply SHT_REL relocations across allocatable sections.
            for sec in elf.iter_sections():
                if sec["sh_type"] != "SHT_REL":
                    continue
                target_idx = sec["sh_info"]
                if target_idx not in sec_by_idx:
                    continue
                t_base, _ = sec_by_idx[target_idx]
                for rel in sec.iter_relocations():
                    sym = symtab.get_symbol(rel["r_info_sym"])
                    shndx = sym["st_shndx"]
                    if shndx == "SHN_UNDEF":
                        target = self.stubs[sym.name]
                    elif isinstance(shndx, int) and shndx in sec_by_idx:
                        target = sec_by_idx[shndx][0] + sym["st_value"]
                    else:
                        continue
                    loc = t_base + rel["r_offset"]
                    rtype = rel["r_info_type"]
                    word = struct.unpack("<I", self.cpu.mem_read(loc, 4))[0]
                    if rtype == 2:  # R_ARM_ABS32
                        self.cpu.mem_write(loc, struct.pack("<I", (word + target) & 0xFFFFFFFF))
                    elif rtype in (28, 29):  # R_ARM_CALL / R_ARM_JUMP24
                        addend = (_s24(word & 0xFFFFFF) << 2) + 8
                        dest = target + addend
                        delta = dest - (loc + 8)
                        assert -0x02000000 <= delta < 0x02000000, f"Branch out of range at 0x{loc:x}: {delta}"
                        imm24 = (delta >> 2) & 0xFFFFFF
                        self.cpu.mem_write(loc, struct.pack("<I", (word & 0xFF000000) | imm24))
                    else:
                        raise ValueError(f"Unsupported relocation type {rtype} in {sec.name}")

    def _setup_runtime(self):
        self.cpu.mem_map(STACK_BASE, 0x4000)
        self.cpu.mem_map(STOP_ADDR, 0x1000)
        self.cpu.mem_map(TASK_BASE, 0x1000)
        # Populate current_thread_info()->task at (SP & ~0x1fff) + 0xc.
        task_struct = TASK_BASE + 0x100
        thread_group = TASK_BASE + 0x400
        self.cpu.mem_write(STACK_BASE + 0x2000 + 0xC, struct.pack("<I", task_struct))
        self.cpu.mem_write(task_struct + 0x8, struct.pack("<I", thread_group))
        self.cpu.mem_write(task_struct + 0x104, struct.pack("<I", 0))
        self.cpu.mem_write(task_struct + 0x108, struct.pack("<I", 0))
        self.cpu.mem_write(thread_group + 0x14, struct.pack("<I", 0))

        self.cpu.hook_add(UC_HOOK_MEM_WRITE, self._on_mem_write)
        self.cpu.hook_add(UC_HOOK_MEM_READ, self._on_mem_read)
        self.cpu.hook_add(UC_HOOK_CODE, self._on_stub_code, begin=STUB_BASE, end=STUB_BASE + 0x3FFF)

    def _on_mem_write(self, cpu, access, address, size, value, _):
        if address >= 0xF0000000:
            self.mmio_writes.append((address, size, value))
            self.events.append(("write", address, size, value))

    def _on_mem_read(self, cpu, access, address, size, value, _):
        if address >= 0xF0000000:
            actual = int.from_bytes(cpu.mem_read(address, size), "little")
            self.mmio_reads.append((address, size, actual))
            self.events.append(("read", address, size, actual))

    def _on_stub_code(self, cpu, address, size, _):
        handler = self.stub_handlers.get(address)
        if handler is not None:
            handler(cpu)

    def set_stub(self, name, fn):
        if name in self.stubs:
            self.stub_handlers[self.stubs[name]] = fn

    def _register_default_stubs(self):
        def on_outer_sync(_cpu):
            self.events.append(("outer_cache_sync",))

        def on_memcpy(cpu):
            dst, src, n = (cpu.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
            if n:
                cpu.mem_write(dst, bytes(cpu.mem_read(src, n)))
            cpu.reg_write(UC_ARM_REG_R0, dst)

        def on_memset(cpu):
            dst, val, n = (cpu.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
            if n:
                cpu.mem_write(dst, bytes([val & 0xFF]) * n)
            cpu.reg_write(UC_ARM_REG_R0, dst)

        def on_memzero(cpu):
            dst, n = cpu.reg_read(UC_ARM_REG_R0), cpu.reg_read(UC_ARM_REG_R1)
            if n:
                cpu.mem_write(dst, b"\x00" * n)

        def on_bug(_cpu):
            raise AssertionError("Module hit __bug_noarg during offline contract check")

        def ret_zero(cpu):
            cpu.reg_write(UC_ARM_REG_R0, 0)

        if hasattr(self, "outer_cache_sync_addr"):
            self.stub_handlers[self.outer_cache_sync_addr] = on_outer_sync
        self.set_stub("memcpy", on_memcpy)
        self.set_stub("memset", on_memset)
        self.set_stub("__memzero", on_memzero)
        self.set_stub("__bug_noarg", on_bug)
        for noop_zero in (
            "printk",
            "__migrate_disable",
            "__migrate_enable",
            "rt_spin_lock",
            "rt_spin_unlock",
            "_raw_spin_lock_irqsave",
            "_raw_spin_unlock_irqrestore",
            "_mutex_lock",
            "_mutex_unlock",
            "__rt_mutex_init",
            "__mutex_do_init",
            "__rt_spin_lock_init",
            "__udif_request_irq",
            "__udif_free_irq",
            "udif_create_proc",
            "udif_remove_proc",
            "udif_cdev_register",
            "udif_cdev_unregister",
            "udif_driver_register",
            "udif_driver_unregister",
        ):
            self.set_stub(noop_zero, ret_zero)

    def map_mmio(self, base, size):
        self.cpu.mem_map(base, size)

    def clear_logs(self):
        self.events.clear()
        self.mmio_writes.clear()
        self.mmio_reads.clear()

    def call(self, addr, args=(), max_steps=50000):
        stack = STACK_BASE + 0x3F00
        for reg, val in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            self.cpu.reg_write(reg, val & 0xFFFFFFFF)
        self.cpu.reg_write(UC_ARM_REG_SP, stack)
        self.cpu.reg_write(UC_ARM_REG_LR, STOP_ADDR)
        self.cpu.emu_start(addr, STOP_ADDR, count=max_steps)
        assert self.cpu.reg_read(UC_ARM_REG_PC) == STOP_ADDR, f"Did not return from 0x{addr:x}"
        assert self.cpu.reg_read(UC_ARM_REG_SP) == stack, f"Stack imbalance at 0x{addr:x}"
        return self.cpu.reg_read(UC_ARM_REG_R0)

    def read_cstr(self, addr, limit=256):
        raw = bytes(self.cpu.mem_read(addr, limit))
        return raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")


def _audit_xdmac(repo):
    ko = repo / ".local/dumps/initrd_extracted/kmod/dmac.ko"
    emu = ArmModuleEmulator(ko, DMAC_SHA256)
    emu.map_mmio(0xF0000000, 0x20000)

    # Map DDR0/DDR1 kernel VA windows for ___dma_single_cpu_to_dev tests.
    emu.cpu.mem_map(0x70000000, 0x4000)
    emu.cpu.mem_map(0xA1000000, 0x4000)

    dma_calls = []

    def on_dma_cpu_to_dev(cpu):
        dma_calls.append((
            cpu.reg_read(UC_ARM_REG_R0),
            cpu.reg_read(UC_ARM_REG_R1),
            cpu.reg_read(UC_ARM_REG_R2),
        ))
        emu.events.append(("dma_single_cpu_to_dev", dma_calls[-1][0], dma_calls[-1][1], dma_calls[-1][2]))

    emu.set_stub("___dma_single_cpu_to_dev", on_dma_cpu_to_dev)

    proc_captures = []

    def on_scnprintf(cpu):
        buf = cpu.reg_read(UC_ARM_REG_R0)
        size = cpu.reg_read(UC_ARM_REG_R1)
        fmt = emu.read_cstr(cpu.reg_read(UC_ARM_REG_R2))
        val = cpu.reg_read(UC_ARM_REG_R3)
        proc_captures.append((fmt, val))
        text = (fmt % val) if "%" in fmt else fmt
        encoded = text[: max(size - 1, 0)].encode("ascii")
        if size > 0:
            emu.cpu.mem_write(buf, encoded + b"\x00")
        cpu.reg_write(UC_ARM_REG_R0, len(encoded))

    emu.set_stub("scnprintf", on_scnprintf)

    # Seed UDIF_DEVICE + UDIF_CHANNELS[8] (0xf0000000 for ch 0..3, 0xf0010000 for ch 4..7) and run dmac_probe.
    dev_struct = 0x70003000
    chs_array = 0x70003100
    emu.cpu.mem_write(dev_struct + 0x14, struct.pack("<I", chs_array))
    for ch in range(8):
        base = 0xF0000000 if ch < 4 else 0xF0010000
        emu.cpu.mem_write(chs_array + ch * 0x5C + 0x10, struct.pack("<I", base))
        assert emu.call(emu.symbols["dmac_probe"], [dev_struct, ch, 0]) == 0

    unit_bases = [emu.call(emu.symbols["boss_lld_get_base_addr_dmac"], [0]),
                  emu.call(emu.symbols["boss_lld_get_base_addr_dmac"], [4])]
    assert unit_bases == [0xF0000000, 0xF0010000], unit_bases
    ch_bases = [emu.call(emu.symbols["boss_lld_get_base_addr_dmac_ch"], [ch]) for ch in range(8)]
    expected_ch = [
        0xF0000010, 0xF0000040, 0xF0000070, 0xF00000A0,
        0xF0010010, 0xF0010040, 0xF0010070, 0xF00100A0,
    ]
    assert ch_bases == expected_ch, ch_bases
    # Verify invalid channel 8 is rejected with -EINVAL by dmac_mem_transfer_async.
    bad_req = 0x70002C00
    emu.cpu.mem_write(bad_req, struct.pack("<IIII", 8, 0x10001000, 0x11112222, 0))
    assert emu.call(emu.symbols["dmac_mem_transfer_async"], [bad_req]) == 0xFFFFFFEA

    # Verify unit & channel proc register labels against exact MMIO offsets.
    proc_buf = 0x70002000
    proc_desc = 0x70002800
    emu.cpu.mem_write(proc_desc, struct.pack("<II", proc_buf, 1024))
    emu.cpu.mem_write(0xF0000000, struct.pack("<I", 0xA0000000))
    proc_captures.clear()
    emu.call(emu.symbols["boss_hw_dmac_proc_setbuf_reg_unit"], [proc_desc, 0, 0xF0000000])
    assert proc_captures == [("reg_base: 0x%08X\n", 0xF0000000), ("XDACS: 0x%08X\n", 0xA0000000)], proc_captures

    ch_sentinels = [0xB0000000 + i for i in range(9)]
    for i, val in enumerate(ch_sentinels):
        emu.cpu.mem_write(0xF0010040 + i * 4, struct.pack("<I", val))
    proc_captures.clear()
    emu.call(emu.symbols["boss_hw_dmac_proc_setbuf_reg_ch"], [proc_desc, 0, 0xF0010040])
    expected_labels = ["XDTBC", "XDSSA", "XDDSA", "XDSAC", "XDDAC", "XDDCC", "XDDES", "XDDPC", "XDDSD"]
    assert proc_captures[0] == ("reg_base: 0x%08X\n", 0xF0010040)
    assert [(fmt.split(":")[0], val) for fmt, val in proc_captures[1:]] == list(zip(expected_labels, ch_sentinels))

    # Unit enable (fixed=0, round-robin=1).
    unit_enable_cases = []
    for unit_base, mode, expected in [(0xF0000000, 0, 0x10000000), (0xF0010000, 1, 0x11000000)]:
        emu.clear_logs()
        emu.call(emu.symbols["boss_hw_dmac_unit_enable"], [unit_base, mode])
        assert emu.mmio_writes == [(unit_base, 4, expected)]
        assert ("outer_cache_sync",) in emu.events
        unit_enable_cases.append({"unit_base": hex(unit_base), "round_robin": mode, "written": hex(expected)})

    # Start transfer + coherency fence (DDR0 and DDR1 LLI descriptor physical addresses).
    start_cases = []
    for ch_base, lli_phys, lli_va in [
        (0xF0010040, 0x10001000, 0x70001000),
        (0xF0000010, 0x81002000, 0xA1002000),
    ]:
        words = [0x11110000 + i for i in range(6)]
        emu.cpu.mem_write(lli_va, struct.pack("<6I", *words))
        dma_calls.clear()
        emu.clear_logs()
        emu.call(emu.symbols["boss_hw_dmac_start_transfer"], [ch_base, lli_phys])
        assert dma_calls == [(lli_va, 0x30, 2)], dma_calls
        expected_writes = [(ch_base + i * 4, 4, words[i]) for i in range(6)] + [
            (ch_base + 0x1C, 4, 0x11),
            (ch_base + 0x18, 4, 0x11108003),
        ]
        assert emu.mmio_writes == expected_writes, emu.mmio_writes
        assert emu.events[0][0] == "dma_single_cpu_to_dev"
        assert sum(1 for ev in emu.events if ev == ("outer_cache_sync",)) == 8
        start_cases.append({
            "channel_base": hex(ch_base),
            "lli_phys": hex(lli_phys),
            "cache_clean_va": hex(lli_va),
            "cache_clean_bytes": 0x30,
            "cache_clean_dir": 2,
            "write_order": [
                {"offset": hex(addr - ch_base), "name": expected_labels[(addr - ch_base) // 4], "value": hex(val)}
                for addr, _, val in emu.mmio_writes
            ],
        })

    # Transfer result status & XDDSD clear.
    result_cases = []
    for xddsd, exp_rc in [(0x8, 0), (0x18, 0), (0x4, 0xFFFFFFF3), (0x0, 0xFFFFFFF3)]:
        emu.cpu.mem_write(0xF0010060, struct.pack("<I", xddsd))
        emu.clear_logs()
        rc = emu.call(emu.symbols["boss_hw_dmac_get_transfer_result"], [0xF0010040])
        assert rc == exp_rc, (hex(xddsd), hex(rc))
        assert emu.mmio_writes == [(0xF0010060, 4, 0)]
        result_cases.append({"xddsd": hex(xddsd), "return_code_s32": rc - 0x100000000 if rc & 0x80000000 else rc, "cleared_offset": "0x20"})

    # Shutdown disables channel via XDDES = 0.
    emu.clear_logs()
    emu.call(emu.symbols["boss_hw_dmac_shutdown"], [0xF0010040])
    assert emu.mmio_writes == [(0xF0010058, 4, 0)]

    return {
        "module": ".local/dumps/initrd_extracted/kmod/dmac.ko",
        "sha256": emu.sha256,
        "current_body_module_identity_checked": False,
        "unit_bases": [hex(x) for x in unit_bases],
        "channel_bases": {str(i): hex(ch_bases[i]) for i in range(8)},
        "invalid_channel_8_rejected_einval": True,
        "unit_registers": [{"offset": "0x0", "name": "XDACS", "access_width_bits": 32}],
        "channel_registers": [{"offset": hex(i * 4), "name": lbl, "access_width_bits": 32} for i, lbl in enumerate(expected_labels)],
        "unit_enable_cases": unit_enable_cases,
        "start_transfer_cases": start_cases,
        "transfer_result_cases": result_cases,
        "shutdown_write": {"offset": "0x18", "name": "XDDES", "value": "0x0"},
        "async_request_layout": {
            "0x00": "channel (0..7)",
            "0x04": "lli_phys (48-byte descriptor physical address)",
            "0x08": "callback (non-null function pointer: void (*)(int result, void *arg))",
            "0x0c": "callback_arg",
            "0x10": "kernel list_head (queued while channel busy)",
        },
        "read_or_write_permission": False,
    }


def _decode_pl330_block(block):
    """Verify key PL330 instruction opcodes present in a .data template block."""
    assert block[0:2] == b"\xbc\x00", block[:4].hex()
    assert block[6:8] == b"\xbc\x02", block[6:10].hex()
    assert block[12:14] == b"\xbc\x01", block[12:16].hex()
    return {
        "dmamov_sar_offset": "0x02",
        "dmamov_dar_offset": "0x08",
        "initial_ccr_le32": hex(struct.unpack_from("<I", block, 14)[0]),
    }


def _audit_dma330(repo):
    ko = repo / ".local/dumps/camera_2025/usr/usr/kmod/dma330.ko"
    emu = ArmModuleEmulator(ko, DMA330_SHA256)
    emu.map_mmio(0xF0030000, 0x10000)

    # Noncached microcode buffer + sample DMA physical-to-VA/noncache maps.
    ucode_pa = 0x14000000
    ucode_va = 0x71000000
    emu.cpu.mem_map(ucode_va, 0x40000)
    data_va = 0x72000000
    emu.cpu.mem_map(data_va, 0x10000)

    def phys_to_va(cpu):
        pa = cpu.reg_read(UC_ARM_REG_R0)
        if ucode_pa <= pa < ucode_pa + 0x40000:
            cpu.reg_write(UC_ARM_REG_R0, ucode_va + (pa - ucode_pa))
        elif 0x12340000 <= pa < 0x12350000:
            cpu.reg_write(UC_ARM_REG_R0, data_va + (pa - 0x12340000))
        else:
            cpu.reg_write(UC_ARM_REG_R0, 0)

    def va_to_phys(cpu):
        va = cpu.reg_read(UC_ARM_REG_R0)
        if ucode_va <= va < ucode_va + 0x40000:
            cpu.reg_write(UC_ARM_REG_R0, ucode_pa + (va - ucode_va))
        elif data_va <= va < data_va + 0x10000:
            cpu.reg_write(UC_ARM_REG_R0, 0x12340000 + (va - data_va))
        else:
            cpu.reg_write(UC_ARM_REG_R0, 0)

    emu.set_stub("arch_phys_to_noncache", phys_to_va)
    emu.set_stub("arch_phys_to_va", phys_to_va)
    emu.set_stub("arch_va_to_phys", va_to_phys)

    sync_calls = []

    def on_snd_sync_direct(cpu):
        sync_calls.append(cpu.reg_read(UC_ARM_REG_R0))
        cpu.reg_write(UC_ARM_REG_R0, 0)

    emu.set_stub("osal_snd_sync_direct", on_snd_sync_direct)

    # Seed UDIF_DEVICE + UDIF_CHANNELS[5] + driver_info microcode VA + drv_state[0..3]=1.
    bss_base = emu.sections[".bss"][1]
    dev_struct = 0x72008000
    chs_array = 0x72008100
    emu.cpu.mem_write(dev_struct + 0x14, struct.pack("<I", chs_array))
    for ch in range(4):
        emu.cpu.mem_write(chs_array + ch * 0x5C + 0x10, struct.pack("<I", 0xF0030000))
        emu.cpu.mem_write(bss_base + (0xE4 + ch) * 4, struct.pack("<I", 1))
    emu.cpu.mem_write(bss_base + 0x10, struct.pack("<I", ucode_va))

    # Execute original dma330_probe for channels 0..3 and 4 (abort).
    for ch in range(5):
        rc = emu.call(emu.symbols["dma330_probe"], [dev_struct, ch, 0])
        assert rc == 0, (ch, rc)

    # Read back all 52 MMIO pointers populated at .bss+0x3b4..0x58c.
    slot_names = [
        (0x3B4, "dsr"), (0x3BC, "dpc"), (0x3C4, "inten"), (0x3CC, "int_event_ris"),
        (0x3D4, "intmis"), (0x3DC, "intclr"), (0x3E4, "fsrd"), (0x3EC, "fsrc"), (0x3F4, "ftrd"),
    ]
    for ch in range(4):
        slot_names += [
            (0x3FC + ch * 8, f"ftr[{ch}]"),
            (0x41C + ch * 8, f"csr[{ch}]"),
            (0x43C + ch * 8, f"cpc[{ch}]"),
            (0x45C + ch * 8, f"sar[{ch}]"),
            (0x47C + ch * 8, f"dar[{ch}]"),
            (0x49C + ch * 8, f"ccr[{ch}]"),
            (0x4BC + ch * 8, f"lc0[{ch}]"),
            (0x4DC + ch * 8, f"lc1[{ch}]"),
        ]
    slot_names += [
        (0x4FC, "dbgstatus"), (0x504, "dbgcmd"), (0x50C, "dbginst0"), (0x514, "dbginst1"),
    ]
    for i in range(5):
        slot_names.append((0x51C + i * 8, f"cr[{i}]"))
    slot_names += [(0x544, "crd"), (0x54C, "wd")]
    for i in range(4):
        slot_names.append((0x554 + i * 8, f"periph_id_n[{i}]"))
    for i in range(4):
        slot_names.append((0x574 + i * 8, f"pcell_id_n[{i}]"))

    reg_map = {}
    for bss_off, name in slot_names:
        ptr = struct.unpack("<I", emu.cpu.mem_read(bss_base + bss_off, 4))[0]
        assert 0xF0030000 <= ptr < 0xF0031000, (name, hex(ptr))
        reg_map[name] = hex(ptr - 0xF0030000)

    expected_offsets = {
        "dsr": "0x0", "dpc": "0x4", "inten": "0x20", "int_event_ris": "0x24",
        "intmis": "0x28", "intclr": "0x2c", "fsrd": "0x30", "fsrc": "0x34", "ftrd": "0x38",
        "ftr[0]": "0x40", "ftr[3]": "0x4c", "csr[0]": "0x100", "cpc[0]": "0x104",
        "sar[0]": "0x400", "dar[0]": "0x404", "ccr[0]": "0x408", "lc0[0]": "0x40c", "lc1[0]": "0x410",
        "sar[3]": "0x460", "lc1[3]": "0x470",
        "dbgstatus": "0xd00", "dbgcmd": "0xd04", "dbginst0": "0xd08", "dbginst1": "0xd0c",
        "cr[0]": "0xe00", "cr[4]": "0xe10", "crd": "0xe14", "wd": "0xe80",
        "periph_id_n[0]": "0xfe0", "pcell_id_n[0]": "0xff0", "pcell_id_n[3]": "0xffc",
    }
    for k, v in expected_offsets.items():
        assert reg_map[k] == v, (k, reg_map[k], v)

    # Test intclr (.text+0x90) for channels 0..4.
    text_base = emu.sections[".text"][1]
    intclr_cases = []
    for ch in range(5):
        emu.clear_logs()
        emu.call(text_base + 0x90, [ch])
        assert emu.mmio_writes == [(0xF003002C, 4, 1 << ch)]
        intclr_cases.append({"channel": ch, "intclr_write": hex(1 << ch)})

    # Test dmakill (.text+0xa18) on idle DBGSTATUS=0 and stuck-busy DBGSTATUS=1.
    dmakill_cases = []
    emu.cpu.mem_write(0xF0030D00, struct.pack("<I", 0))
    for ch in range(4):
        emu.clear_logs()
        rc = emu.call(text_base + 0xA18, [ch])
        assert rc == 0, rc
        assert emu.mmio_writes == [
            (0xF003002C, 4, 1 << ch),
            (0xF0030D08, 4, 0x00010001 | (ch << 8)),
            (0xF0030D0C, 4, 0),
            (0xF0030D04, 4, 0),
        ], emu.mmio_writes
        dmakill_cases.append({"channel": ch, "dbginst0": hex(0x00010001 | (ch << 8)), "return_code": 0})

    emu.cpu.mem_write(0xF0030D00, struct.pack("<I", 1))
    sync_calls.clear()
    emu.clear_logs()
    rc_busy = emu.call(text_base + 0xA18, [2])
    assert rc_busy == 0xFFFFFFFB and len(sync_calls) == 2, (hex(rc_busy), len(sync_calls))
    assert sum(1 for a, _, _ in emu.mmio_reads if a == 0xF0030D00) == 2

    # Test dmago (.text+0x20f4) for channels 0..3.
    dmago_cases = []
    emu.cpu.mem_write(0xF0030D00, struct.pack("<I", 0))
    for ch in range(4):
        prog_pa = 0x12345000 + ch * 0x100
        prog_va = data_va + (prog_pa - 0x12340000)
        emu.cpu.mem_write(prog_va, b"\xA2" + bytes([ch]) + struct.pack("<I", prog_pa))
        emu.cpu.mem_write(0xF0030020, struct.pack("<I", 0))
        emu.clear_logs()
        rc = emu.call(text_base + 0x20F4, [ch, prog_pa])
        assert rc == 0, rc
        expected_inst0 = (0xA2 << 16) | (ch << 24) | (ch << 8)
        assert emu.mmio_writes == [
            (0xF0030020, 4, 0x10 | (1 << ch)),
            (0xF0030004, 4, prog_pa),
            (0xF0030D08, 4, expected_inst0),
            (0xF0030D0C, 4, prog_pa),
            (0xF0030D04, 4, 0),
        ], emu.mmio_writes
        dmago_cases.append({
            "channel": ch,
            "prog_pa": hex(prog_pa),
            "inten_written": hex(0x10 | (1 << ch)),
            "dbginst0": hex(expected_inst0),
            "dbginst1": hex(prog_pa),
        })

    emu.cpu.mem_write(0xF0030D00, struct.pack("<I", 1))
    emu.clear_logs()
    assert emu.call(text_base + 0x20F4, [0, 0x12345000]) == 0xFFFFFFFB
    assert emu.mmio_writes == []

    # Test end-to-end dma330_mem_transfer_async on ch 0 (1 segment, 0x1000 bytes).
    emu.cpu.mem_write(0xF0030D00, struct.pack("<I", 0))
    emu.cpu.mem_write(0xF0030020, struct.pack("<I", 0))
    area_va = data_va + 0x1000
    area_pa = 0x12341000
    emu.cpu.mem_write(area_va, struct.pack("<III", 0x1000, 0x10200000, 0x10300000))
    req_va = data_va + 0x2000
    # req struct: +0 ch=0, +4 num=1, +8 addr=area_pa, +0xc callback=0x11112222, +0x10 cookies=0x33334444
    emu.cpu.mem_write(req_va, struct.pack("<IIIII", 0, 1, area_pa, 0x11112222, 0x33334444))
    emu.clear_logs()
    rc_async = emu.call(emu.symbols["dma330_mem_transfer_async"], [req_va])
    assert rc_async == 0, hex(rc_async)
    # Capture DPC written by DMAGO inside async submit.
    dpc_write = [v for addr, _, v in emu.mmio_writes if addr == 0xF0030004]
    assert len(dpc_write) == 1
    launched_pa = dpc_write[0]
    launched_va = ucode_va + (launched_pa - ucode_pa)
    # Check array_type 0,1,2,3 base boundaries in ucode_va for channel 0.
    launched_rel = launched_pa - ucode_pa
    if launched_rel < 0x4510:
        selected_array = 0
    elif launched_rel < 0x4510 + 0x3510:
        selected_array = 1
    elif launched_rel < 0x4510 + 0x3510 + 0x2910:
        selected_array = 2
    else:
        selected_array = 3
    emitted_head = bytes(emu.cpu.mem_read(launched_va, 24)).hex()

    # Inspect the 4 .data template arrays directly.
    data_sec = ko.read_bytes()
    with ko.open("rb") as f:
        data_bytes = ELFFile(f).get_section_by_name(".data").data()
    arrays = []
    for idx, (off, ch_stride, blk_sz) in enumerate([
        (0x00000, 0x4510, 0x45),
        (0x11440, 0x3510, 0x35),
        (0x1E880, 0x2910, 0x29),
        (0x28CC0, 0x2110, 0x21),
    ]):
        hdr = data_bytes[off : off + 8]
        blk0 = data_bytes[off + 8 : off + 8 + blk_sz]
        tail = data_bytes[off + 8 + 256 * blk_sz : off + ch_stride]
        assert hdr == b"\xA2\x00\x00\x00\x00\x00\x00\x00"
        assert tail == b"\x13\x34\x00\x00\x00\x00\x00\x00"
        info = _decode_pl330_block(blk0)
        info.update({
            "array_type": idx,
            "data_section_offset": hex(off),
            "channel_stride_bytes": hex(ch_stride),
            "max_segments": 256,
            "segment_stride_bytes": hex(blk_sz),
            "tail_opcodes_hex": tail.hex(),
        })
        arrays.append(info)

    return {
        "module": ".local/dumps/camera_2025/usr/usr/kmod/dma330.ko",
        "sha256": emu.sha256,
        "current_body_module_identity_checked": False,
        "mmio_base": "0xf0030000",
        "channels": 4,
        "register_offsets": reg_map,
        "intclr_cases": intclr_cases,
        "dmakill_cases": dmakill_cases,
        "dmakill_busy_returns_eio": -5,
        "dmago_cases": dmago_cases,
        "dmago_busy_returns_eio": -5,
        "async_transfer_sample": {
            "size_bytes": "0x1000",
            "src_pa": "0x10200000",
            "dst_pa": "0x10300000",
            "selected_array_type": selected_array,
            "launched_prog_pa": hex(launched_pa),
            "program_header_24bytes_hex": emitted_head,
            "dmac_data_cache_flushed_by_driver": False,
        },
        "microcode_template_arrays": arrays,
        "async_request_layout": {
            "0x00": "channel (0..3)",
            "0x04": "num_segments (1..256)",
            "0x08": "area_info_pa (12B entries: size, src_pa, dst_pa)",
            "0x0c": "callback (non-null function pointer)",
            "0x10": "cookies",
        },
        "coherency_note": "dma330.ko accesses its own microcode via arch_phys_to_noncache and guards MMIO writes with DSB SY + outer_cache+0x1c; caller data cache clean/invalidate is not performed by dma330_mem_transfer_async.",
        "read_or_write_permission": False,
    }


def audit(repo):
    return {
        "schema_version": 1,
        "status": "offline-original-instruction-dma-contracts-verified",
        "camera_access_performed": False,
        "read_or_write_permission": False,
        "xdmac": _audit_xdmac(repo),
        "dma330": _audit_dma330(repo),
        "limits": [
            "Verified against saved initrd/camera_2025 module copies in Unicorn; live-body module hashes remain unchecked",
            "MMIO register writes and microcode generation were verified in emulation; no hardware transfers ran",
            "Physical buffer ownership and sensor/DFE-to-USB DMA wiring remain open",
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
        "xdmac_channels": len(result["xdmac"]["channel_bases"]),
        "xdmac_ch_regs": len(result["xdmac"]["channel_registers"]),
        "dma330_regs": len(result["dma330"]["register_offsets"]),
        "dma330_template_arrays": len(result["dma330"]["microcode_template_arrays"]),
        "camera_access_performed": False,
    }))
