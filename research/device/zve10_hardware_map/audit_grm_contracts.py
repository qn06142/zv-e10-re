"""Offline GRM / Sugilite GPU / MA / OSD DataflowInfra contract audit.

Executes verified local Sony binaries (grm_gles.ko, grm_ma.ko, dataflowInfraFramework.so)
and verifies current-body libObj.so OSD submission offsets in Unicorn without hardware access.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

from elftools.elf.elffile import ELFFile
from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_THUMB, Uc
from unicorn.arm_const import (
    UC_ARM_REG_LR,
    UC_ARM_REG_R0,
    UC_ARM_REG_R1,
    UC_ARM_REG_R2,
    UC_ARM_REG_R3,
    UC_ARM_REG_SP,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_dma_contracts import ArmModuleEmulator, STOP_ADDR


GRM_GLES_SHA256 = "4e4b99e5e17e170ddc13dc432178299512525debd6fb19512521b38867da7a65"
GRM_MA_SHA256 = "c21479fea7b0bc081f72315c0b0b514b383a58b5a3bb5f2fefbfd26e20711879"
DATAFLOW_SHA256 = "3a7235ab96ed87606fc598f45db8e318afacc1e58a07e51b541923a43de76941"
LIBOBJ_SHA256 = "bc0deb2f0e94218752e42ce6f5a3576d7456971eb63fbde705ffbd9b3a7fdeea"


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _audit_grm_gles(repo):
    ko = repo / ".local/dumps/camera_2025/usr/usr/kmod/grm_gles.ko"
    emu = ArmModuleEmulator(ko, GRM_GLES_SHA256)
    emu.map_mmio(0xF1000000, 0x20000)
    emu.map_mmio(0xF2804000, 0x2000)
    emu.map_mmio(0xF3400000, 0x1000)

    scratch = 0x70000000
    emu.cpu.mem_map(scratch, 0x4000)
    dev_struct = scratch + 0x100
    # Populate dev struct: [dev+0xf8] = 0xf1000000 (MMIO base), [dev+0xf0] = 0 (param), locks/lists zeroed
    emu.cpu.mem_write(dev_struct + 0xF8, struct.pack("<I", 0xF1000000))
    emu.cpu.mem_write(dev_struct + 0xF0, struct.pack("<I", 0))

    udelays = []
    wake_ups = []
    completions = []
    osal_sends = []
    allocs = []
    msg_buf = scratch + 0x1000

    def on_udelay(cpu):
        udelays.append(f"0x{cpu.reg_read(UC_ARM_REG_R0):x}")

    def on_wake_up(cpu):
        wake_ups.append(f"0x{cpu.reg_read(UC_ARM_REG_R0):x}")

    def on_complete_all(cpu):
        completions.append(f"0x{cpu.reg_read(UC_ARM_REG_R0):x}")

    def on_valloc(cpu):
        ptr_out = cpu.reg_read(UC_ARM_REG_R1)
        emu.cpu.mem_write(ptr_out, struct.pack("<I", msg_buf + 0x10))
        cpu.reg_write(UC_ARM_REG_R0, 0)

    def on_snd_msg(cpu):
        osal_sends.append((f"0x{cpu.reg_read(UC_ARM_REG_R0):x}", f"0x{cpu.reg_read(UC_ARM_REG_R1):x}"))
        cpu.reg_write(UC_ARM_REG_R0, 0)

    def on_kmalloc(cpu):
        allocs.append(cpu.reg_read(UC_ARM_REG_R0))
        cpu.reg_write(UC_ARM_REG_R0, scratch + 0x2000)

    def ret_zero(cpu):
        cpu.reg_write(UC_ARM_REG_R0, 0)

    emu.set_stub("__const_udelay", on_udelay)
    emu.set_stub("__wake_up", on_wake_up)
    emu.set_stub("complete_all", on_complete_all)
    emu.set_stub("osal_valloc_msg_wait", on_valloc)
    emu.set_stub("osal_snd_msg", on_snd_msg)
    emu.set_stub("osal_free_msg", ret_zero)
    emu.set_stub("kmem_cache_alloc", on_kmalloc)
    emu.set_stub("_set_bit", ret_zero)
    emu.set_stub("_clear_bit", ret_zero)

    # 1. sugilite_clock_up_internal
    for reg, init in ((0xF28040C4, 0xAAAA0007), (0xF28041A8, 0xBBBB0007), (0xF28050B8, 0xCCCC0007), (0xF280518C, 0xDDDD0007)):
        emu.cpu.mem_write(reg, struct.pack("<I", init))
    emu.clear_logs()
    emu.call(emu.symbols["sugilite_clock_up_internal"])
    clock_up_writes = [
        {"address": f"0x{a:08x}", "size": s, "value": f"0x{v:08x}"}
        for a, s, v in emu.mmio_writes
    ]
    assert [w["address"] for w in clock_up_writes] == [
        "0xf28040c4",
        "0xf28041a8",
        "0xf28050b8",
        "0xf280518c",
        "0xf3400080",
        "0xf3400280",
    ], clock_up_writes
    assert udelays == ["0x1a36e"], udelays

    # 2. sugilite_clock_down_internal
    udelays.clear()
    emu.clear_logs()
    emu.call(emu.symbols["sugilite_clock_down_internal"])
    clock_down_writes = [
        {"address": f"0x{a:08x}", "size": s, "value": f"0x{v:08x}"}
        for a, s, v in emu.mmio_writes
    ]
    assert [w["address"] for w in clock_down_writes] == [
        "0xf3400084",
        "0xf3400284",
        "0xf28040c4",
        "0xf28041a8",
        "0xf28050b8",
        "0xf280518c",
    ], clock_down_writes

    # 3. sugilite_register_init(dev)
    emu.clear_logs()
    emu.call(emu.symbols["sugilite_register_init"], args=(dev_struct,))
    reg_init_writes = [
        {"address": f"0x{a:08x}", "size": s, "value": f"0x{v:08x}"}
        for a, s, v in emu.mmio_writes
    ]
    assert len(reg_init_writes) == 21, len(reg_init_writes)
    assert reg_init_writes[0] == {"address": "0xf10010c0", "size": 4, "value": "0xffffffff"}
    assert {"address": "0xf1001080", "size": 4, "value": "0x12345678"} in reg_init_writes, reg_init_writes
    assert {"address": "0xf1000050", "size": 4, "value": "0x22222113"} in reg_init_writes, reg_init_writes

    # 4. sugilite_interrupt(irq, dev) with status bits set at 0xf1000034 (bits 31, 30, 26, 0)
    emu.cpu.mem_write(0xF1000034, struct.pack("<I", 0xC4000001))
    emu.cpu.mem_write(0xF1000C18, struct.pack("<I", 0x99ABCDEF))
    emu.cpu.mem_write(0xF1001000, struct.pack("<I", 0x0000000F))
    emu.cpu.mem_write(dev_struct + 0x10, struct.pack("<I", dev_struct + 0x10))
    emu.cpu.mem_write(dev_struct + 0x14, struct.pack("<I", dev_struct + 0x10))
    emu.clear_logs()
    irq_ret = emu.call(emu.symbols["sugilite_interrupt"], args=(76, dev_struct))
    irq_reads = [{"address": f"0x{a:08x}", "size": s, "value": f"0x{v:08x}"} for a, s, v in emu.mmio_reads]
    irq_writes = [{"address": f"0x{a:08x}", "size": s, "value": f"0x{v:08x}"} for a, s, v in emu.mmio_writes]
    assert irq_ret == 1, irq_ret

    # Extract ioctl command literals from sugilite_ioctl literal pool (0x12b8..0x12d0)
    raw = ko.read_bytes()
    with ko.open("rb") as f:
        txt = ELFFile(f).get_section_by_name(".text").data()
    ioctl_literals = [f"0x{struct.unpack_from('<I', txt, off)[0]:08x}" for off in range(0x12B8, 0x12D4, 4)]

    return {
        "path": ".local/dumps/camera_2025/usr/usr/kmod/grm_gles.ko",
        "sha256": emu.sha256,
        "clock_up_writes": clock_up_writes,
        "clock_up_udelay_raw": "0x1a36e",
        "clock_down_writes": clock_down_writes,
        "register_init_writes": reg_init_writes,
        "interrupt_audit": {
            "return_value": irq_ret,
            "reads": irq_reads,
            "ack_writes": irq_writes,
            "woke_waitqueues": wake_ups,
            "completed_all": completions,
        },
        "ioctl_literal_commands": ioctl_literals,
        "mmap_size_classes": {
            "0x200": "512B control/status mapping",
            "0x20000": "128 KiB vmalloc page buffer (dev+0xac) via vmalloc_to_pfn + remap_pfn_range",
            "0x2000000": "32 MiB carveout/aperture",
            "0x4000_default": "16 KiB direct MMIO at PFN 0xf1000 (physical 0xf1000000)",
        },
    }


def _audit_grm_ma(repo):
    ko = repo / ".local/dumps/camera_2025/usr/usr/kmod/grm_ma.ko"
    emu = ArmModuleEmulator(ko, GRM_MA_SHA256)
    scratch = 0x70000000
    emu.cpu.mem_map(scratch, 0x8000)

    dma_ops = []
    uipc_msgs = []
    msg_buf = scratch + 0x1000

    def on_dma_cpu_to_dev(cpu):
        dma_ops.append(
            {
                "va": f"0x{cpu.reg_read(UC_ARM_REG_R0):08x}",
                "size": cpu.reg_read(UC_ARM_REG_R1),
                "direction": cpu.reg_read(UC_ARM_REG_R2),
            }
        )

    def on_phys_to_cache(cpu):
        pa = cpu.reg_read(UC_ARM_REG_R0)
        cpu.reg_write(UC_ARM_REG_R0, (pa - 0xA0000000) & 0xFFFFFFFF if pa >= 0xA0000000 else pa)

    def on_valloc(cpu):
        ep = cpu.reg_read(UC_ARM_REG_R0)
        ptr_out = cpu.reg_read(UC_ARM_REG_R1)
        size = cpu.reg_read(UC_ARM_REG_R2)
        emu.cpu.mem_write(ptr_out, struct.pack("<I", msg_buf + 0x10))
        uipc_msgs.append({"op": "valloc", "ep": f"0x{ep:08x}", "size": size})
        cpu.reg_write(UC_ARM_REG_R0, 0)

    def on_snd_msg(cpu):
        ep = cpu.reg_read(UC_ARM_REG_R0)
        msg = cpu.reg_read(UC_ARM_REG_R1)
        words = struct.unpack("<6I", emu.cpu.mem_read(msg, 24))
        uipc_msgs.append({"op": "snd", "ep": f"0x{ep:08x}", "payload_words": [f"0x{w:08x}" for w in words]})
        cpu.reg_write(UC_ARM_REG_R0, 0)

    def on_rcv_msg_tmo(cpu):
        ptr_out = cpu.reg_read(UC_ARM_REG_R1)
        last = next(m for m in reversed(uipc_msgs) if m["op"] == "snd")
        cmd = int(last["payload_words"][0], 0) & 0xFFFF
        seq_word = int(last["payload_words"][5], 0) & 0xFFFF
        reply_buf = scratch + 0x2000
        emu.cpu.mem_write(reply_buf, struct.pack("<IIIII", cmd | 0x8000, seq_word << 16, 0, 0x12, 0xA8200000))
        emu.cpu.mem_write(ptr_out, struct.pack("<I", reply_buf))
        cpu.reg_write(UC_ARM_REG_R0, 0)

    def ret_zero(cpu):
        cpu.reg_write(UC_ARM_REG_R0, 0)

    emu.set_stub("___dma_single_cpu_to_dev", on_dma_cpu_to_dev)
    emu.set_stub("arch_phys_to_cache", on_phys_to_cache)
    emu.set_stub("osal_valloc_msg_wait", on_valloc)
    emu.set_stub("osal_snd_msg", on_snd_msg)
    emu.set_stub("osal_rcv_msg_tmo", on_rcv_msg_tmo)
    emu.set_stub("osal_free_msg", ret_zero)

    # Execute ma_cache_flush_impl and ma_cache_invalidate_impl on synthetic MA cache descriptor list
    # List: [count=1, ptr->entry], entry=[pa=0x22000000, size=0x1000]
    entry0 = scratch + 0x200
    lst = scratch + 0x100
    emu.cpu.mem_write(entry0, struct.pack("<II", 0xA8200000, 0x2000))
    emu.cpu.mem_write(lst, struct.pack("<II", 1, entry0))
    # Map cache VA target region (pa - 0xa0000000 + 0xc0000000 -> 0xc8200000? ma_cache_ctl adds 0xa0000000/0xe0000000 and 0x60000000/0x20000000)
    emu.call(emu.symbols["ma_cache_flush_impl"], args=(lst, 0x1000))
    emu.call(emu.symbols["ma_cache_invalidate_impl"], args=(lst, 0x1000))
    # Verify exact ___dma_single_cpu_to_dev directions: 1 = clean/flush, 2 = invalidate
    assert [op["direction"] for op in dma_ops] == [1, 2], dma_ops
    assert all(op["size"] == 0x2000 for op in dma_ops), dma_ops

    # Execute ma_dmm_open_send_recv and ma_dmm_close_send_recv
    id_out = scratch + 0x300
    pa_out = scratch + 0x310
    sz_out = scratch + 0x320
    ret_open = emu.call(emu.symbols["ma_dmm_open_send_recv"], args=(0x4B000, id_out, pa_out, sz_out))
    ret_close = emu.call(emu.symbols["ma_dmm_close_send_recv"], args=(0x12,))
    assert ret_open == 0 and ret_close == 0, (ret_open, ret_close)
    assert [m for m in uipc_msgs if m["op"] == "snd"], uipc_msgs

    return {
        "path": ".local/dumps/camera_2025/usr/usr/kmod/grm_ma.ko",
        "sha256": emu.sha256,
        "cache_ops": dma_ops,
        "dmm_uipc_messages": [m for m in uipc_msgs if m["op"] == "snd"],
    }


def _audit_dataflow_container(raw_df, elf_info):
    """Execute C_DataflowInfra_StdData_OSD::C1 + SetEntry_OsdImageSizeInfo with ELF relocations."""
    segs, syms, dynsym_names, rel_dyn, rel_plt = elf_info
    base = 0x04000000
    stub_base = 0x05000000
    stack_base = 0x06000000
    heap_base = 0x07000000
    stop_base = 0x08000000

    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    cpu.mem_map(base, 0x100000)
    for pv, po, psz in segs:
        cpu.mem_write(base + pv, raw_df[po : po + psz])
    cpu.mem_map(stub_base, 0x1000)
    cpu.mem_map(stack_base, 0x10000)
    cpu.mem_map(heap_base, 0x10000)
    cpu.mem_map(stop_base, 0x1000)

    for off, rtype, rsym in rel_dyn:
        sname = dynsym_names[rsym] if rsym < len(dynsym_names) else ""
        if rtype == 23:  # R_ARM_RELATIVE
            val = struct.unpack("<I", cpu.mem_read(base + off, 4))[0]
            cpu.mem_write(base + off, struct.pack("<I", base + val))
        elif rtype in (2, 21) and sname in syms:  # R_ARM_ABS32 / R_ARM_GLOB_DAT
            cpu.mem_write(base + off, struct.pack("<I", base + syms[sname]))

    ext_stubs = {}
    for idx, (off, rtype, rsym) in enumerate(rel_plt):
        sname = dynsym_names[rsym]
        if sname in syms:
            cpu.mem_write(base + off, struct.pack("<I", base + syms[sname]))
        else:
            addr = stub_base + idx * 4
            cpu.mem_write(addr, struct.pack("<HH", 0x4770, 0xBF00))  # bx lr; nop
            cpu.mem_write(base + off, struct.pack("<I", addr | 1))
            ext_stubs[addr] = sname

    def on_ext_stub(uc, addr, size, _ud):
        name = ext_stubs.get(addr)
        if not name:
            return
        r0 = uc.reg_read(UC_ARM_REG_R0)
        r1 = uc.reg_read(UC_ARM_REG_R1)
        r2 = uc.reg_read(UC_ARM_REG_R2)
        if name == "memset":
            uc.mem_write(r0, bytes([r1 & 0xFF]) * r2)
        elif name in ("memcpy", "__aeabi_memcpy", "__aeabi_memcpy4"):
            uc.mem_write(r0, bytes(uc.mem_read(r1, r2)))
        elif name == "strncmp":
            a = bytes(uc.mem_read(r0, r2))
            b = bytes(uc.mem_read(r1, r2))
            res = 0
            for ca, cb in zip(a, b):
                if ca != cb:
                    res = ca - cb
                    break
                if ca == 0:
                    break
            uc.reg_write(UC_ARM_REG_R0, res & 0xFFFFFFFF)
        else:
            uc.reg_write(UC_ARM_REG_R0, 0)

    cpu.hook_add(UC_HOOK_CODE, on_ext_stub, begin=stub_base, end=stub_base + 0x1000)

    def call_reloc(sym_name, *args):
        for reg, val in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            cpu.reg_write(reg, val & 0xFFFFFFFF)
        cpu.reg_write(UC_ARM_REG_SP, stack_base + 0x8000)
        cpu.reg_write(UC_ARM_REG_LR, stop_base | 1)
        cpu.emu_start(base + (syms[sym_name] | 1), stop_base, count=200000)
        return cpu.reg_read(UC_ARM_REG_R0)

    entry_obj = heap_base + 0x1000
    std_obj = heap_base + 0x2000
    container_buf = heap_base + 0x3000

    call_reloc("_ZN34C_DataflowInfra_Entry_OsdImageSizeC1Ev", entry_obj)
    call_reloc("_ZN34C_DataflowInfra_Entry_OsdImageSize17SetData_Image_NumEj", entry_obj, 1)
    call_reloc("_ZN34C_DataflowInfra_Entry_OsdImageSize21SetData_Image_AddressEjj", entry_obj, 0, 0x22334455)
    call_reloc("_ZN34C_DataflowInfra_Entry_OsdImageSize19SetData_Image_SizeHEjt", entry_obj, 0, 640)
    call_reloc("_ZN34C_DataflowInfra_Entry_OsdImageSize19SetData_Image_SizeVEjt", entry_obj, 0, 480)
    call_reloc("_ZN34C_DataflowInfra_Entry_OsdImageSize28SetData_Image_Target_OffsetHEjt", entry_obj, 0, 0)
    call_reloc("_ZN34C_DataflowInfra_Entry_OsdImageSize28SetData_Image_Target_OffsetVEjt", entry_obj, 0, 0)
    call_reloc("_ZN34C_DataflowInfra_Entry_OsdImageSize26SetData_Image_Target_SizeHEjt", entry_obj, 0, 640)
    call_reloc("_ZN34C_DataflowInfra_Entry_OsdImageSize26SetData_Image_Target_SizeVEjt", entry_obj, 0, 480)
    call_reloc("_ZN34C_DataflowInfra_Entry_OsdImageSize17SetData_Image_SelEjj", entry_obj, 0, 0)
    call_reloc("_ZN34C_DataflowInfra_Entry_OsdImageSize24SetData_Image_Out_TargetEjh", entry_obj, 0, 3)
    call_reloc("_ZN34C_DataflowInfra_Entry_OsdImageSize21SetData_Image_ChannelEjh", entry_obj, 0, 0)
    call_reloc("_ZN34C_DataflowInfra_Entry_OsdImageSize24SetData_Image_Trans_TypeEjh", entry_obj, 0, 0)
    call_reloc("_ZN34C_DataflowInfra_Entry_OsdImageSize30SetData_Image_Read_OrientationEjh", entry_obj, 0, 1)

    call_reloc("_ZN27C_DataflowInfra_StdData_OSDC1Ejjj", std_obj, container_buf, 0x200, 0)
    set_ret = call_reloc(
        "_ZN27C_DataflowInfra_StdData_OSD25SetEntry_OsdImageSizeInfoEP34C_DataflowInfra_Entry_OsdImageSize",
        std_obj,
        entry_obj,
    )
    assert set_ret == 0, hex(set_ret)
    out = bytes(cpu.mem_read(container_buf, 0x100))
    header_magic = out[0x00:0x04].decode("ascii")
    entry_magic = out[0x20:0x24].decode("ascii")
    hdr_words = struct.unpack_from("<8I", out, 0x00)
    ent_words = struct.unpack_from("<8I", out, 0x20)
    pay_words = struct.unpack_from("<7I", out, 0x40)
    assert header_magic == "SSOS" and hdr_words[2] == 1 and hdr_words[3] == 1 and hdr_words[4] == 0x20, hdr_words
    assert entry_magic == "ETRY" and ent_words[1] == 0 and ent_words[2] == 0 and ent_words[3] == 0x40 and ent_words[4] == 0xA0, ent_words
    assert list(pay_words) == [1, 0x22334455, 0x01E00280, 0, 0x01E00280, 0, 0x01000003], pay_words

    return {
        "constructor": "0x000238dc",
        "set_entry_osd_image_size_info": "0x0002392c",
        "header_magic": header_magic,
        "data_format_version": hdr_words[2],
        "entry_sum": hdr_words[3],
        "first_entry_offset": f"0x{hdr_words[4]:08x}",
        "entry_magic": entry_magic,
        "entry_cate_id": ent_words[1],
        "entry_cate_version": ent_words[2],
        "entry_data_offset": f"0x{ent_words[3]:08x}",
        "entry_data_size": f"0x{ent_words[4]:08x}",
        "entry_next_offset": f"0x{ent_words[5]:08x}",
        "payload_offset": f"0x{ent_words[3]:08x}",
        "payload_first_28_bytes_words": [f"0x{w:08x}" for w in pay_words],
    }


def _audit_dataflow_and_libobj(repo):
    df_path = repo / ".local/dumps/camera_2025/usr/usr/lib/dataflowInfraFramework.so"
    obj_path = repo / ".local/dumps/camera_2025/usr/usr/lib/libObj.so"
    df_sha = _sha256(df_path)
    obj_sha = _sha256(obj_path)
    assert df_sha == DATAFLOW_SHA256, df_sha
    assert obj_sha == LIBOBJ_SHA256, obj_sha

    with df_path.open("rb") as f:
        elf = ELFFile(f)
        dynsym = elf.get_section_by_name(".dynsym")
        dynsym_list = list(dynsym.iter_symbols())
        dynsym_names = [s.name for s in dynsym_list]
        segs = [(s["p_vaddr"], s["p_offset"], s["p_filesz"]) for s in elf.iter_segments() if s["p_type"] == "PT_LOAD"]
        syms = {s.name: s["st_value"] for s in dynsym_list if s["st_shndx"] != "SHN_UNDEF" and s.name}
        rel_dyn = [(r["r_offset"], r["r_info_type"], r["r_info_sym"]) for r in elf.get_section_by_name(".rel.dyn").iter_relocations()]
        rel_plt = [(r["r_offset"], r["r_info_type"], r["r_info_sym"]) for r in elf.get_section_by_name(".rel.plt").iter_relocations()]

    raw_df = df_path.read_bytes()
    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    cpu.mem_map(0x00000000, 0x00100000)
    for pv, po, psz in segs:
        cpu.mem_write(pv, raw_df[po : po + psz])
    stack = 0x00F00000
    cpu.mem_map(stack, 0x10000)
    obj_mem = 0x01000000
    cpu.mem_map(obj_mem, 0x1000)
    stop = 0x00E00000
    cpu.mem_map(stop, 0x1000)

    def call_df(name, *args):
        cpu.mem_write(obj_mem, b"\x00" * 0x100)
        for reg, val in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), (obj_mem,) + args):
            cpu.reg_write(reg, val & 0xFFFFFFFF)
        cpu.reg_write(UC_ARM_REG_SP, stack + 0xF000)
        cpu.reg_write(UC_ARM_REG_LR, stop | 1)
        cpu.emu_start(syms[name] | 1, stop, count=10000)
        buf = bytes(cpu.mem_read(obj_mem, 0x60))
        diffs = [(off, struct.unpack_from("<I", buf, off)[0]) for off in range(0, 0x60, 4) if struct.unpack_from("<I", buf, off)[0] != 0]
        return [f"+0x{o:02x}=0x{v:08x}" for o, v in diffs]

    setter_tests = {
        "SetData_Image_Num(val=2)": call_df("_ZN34C_DataflowInfra_Entry_OsdImageSize17SetData_Image_NumEj", 2),
        "SetData_Image_Sel(idx=1, val=3)": call_df("_ZN34C_DataflowInfra_Entry_OsdImageSize17SetData_Image_SelEjj", 1, 3),
        "SetData_Image_Address(idx=0, pa=0x22334455)": call_df("_ZN34C_DataflowInfra_Entry_OsdImageSize21SetData_Image_AddressEjj", 0, 0x22334455),
        "SetData_Image_Address(idx=1, pa=0x22445566)": call_df("_ZN34C_DataflowInfra_Entry_OsdImageSize21SetData_Image_AddressEjj", 1, 0x22445566),
        "SetData_Image_SizeH(idx=0, w=640)": call_df("_ZN34C_DataflowInfra_Entry_OsdImageSize19SetData_Image_SizeHEjt", 0, 640),
        "SetData_Image_SizeV(idx=0, h=480)": call_df("_ZN34C_DataflowInfra_Entry_OsdImageSize19SetData_Image_SizeVEjt", 0, 480),
        "SetData_Image_Target_OffsetH(idx=0, x=12)": call_df("_ZN34C_DataflowInfra_Entry_OsdImageSize28SetData_Image_Target_OffsetHEjt", 0, 12),
        "SetData_Image_Target_OffsetV(idx=0, y=34)": call_df("_ZN34C_DataflowInfra_Entry_OsdImageSize28SetData_Image_Target_OffsetVEjt", 0, 34),
        "SetData_Image_Target_SizeH(idx=0, w=640)": call_df("_ZN34C_DataflowInfra_Entry_OsdImageSize26SetData_Image_Target_SizeHEjt", 0, 640),
        "SetData_Image_Target_SizeV(idx=0, h=480)": call_df("_ZN34C_DataflowInfra_Entry_OsdImageSize26SetData_Image_Target_SizeVEjt", 0, 480),
        "SetData_Image_Out_Target(idx=0, t=1)": call_df("_ZN34C_DataflowInfra_Entry_OsdImageSize24SetData_Image_Out_TargetEjh", 0, 1),
        "SetData_Image_Channel(idx=0, ch=2)": call_df("_ZN34C_DataflowInfra_Entry_OsdImageSize21SetData_Image_ChannelEjh", 0, 2),
        "SetData_Image_Trans_Type(idx=0, tt=3)": call_df("_ZN34C_DataflowInfra_Entry_OsdImageSize24SetData_Image_Trans_TypeEjh", 0, 3),
        "SetData_Image_Read_Orientation(idx=0, ro=1)": call_df("_ZN34C_DataflowInfra_Entry_OsdImageSize30SetData_Image_Read_OrientationEjh", 0, 1),
    }
    assert setter_tests["SetData_Image_Address(idx=0, pa=0x22334455)"] == ["+0x18=0x22334455"], setter_tests
    assert setter_tests["SetData_Image_Address(idx=1, pa=0x22445566)"] == ["+0x30=0x22445566"], setter_tests

    serialized_container = _audit_dataflow_container(raw_df, (segs, syms, dynsym_names, rel_dyn, rel_plt))

    return {
        "dataflowInfraFramework": {
            "path": ".local/dumps/camera_2025/usr/usr/lib/dataflowInfraFramework.so",
            "sha256": df_sha,
            "osd_entry_stride_bytes": 24,
            "osd_entry_field_layout_runs": setter_tests,
            "serialized_container": serialized_container,
        },
        "libObj": {
            "path": ".local/dumps/camera_2025/usr/usr/lib/libObj.so",
            "sha256": obj_sha,
            "plt_SetEntry_OsdImageSizeInfo": "0x001083a8",
            "plt_SetData_Image_Address": "0x00109350",
            "plt_DataflowInfraPin_Send": "0x00109344",
            "osd_submit_helper": "0x006f6f64",
            "type5_osd_builder": "0x006fe064",
            "type5_pin_sender": "0x006fe3b0",
            "type5_record_stride_bytes": 32,
            "type5_record_field_map": {
                "+0x00_u16": "SetData_Image_Target_OffsetH (PLT 0x10b840)",
                "+0x02_u16": "SetData_Image_Target_OffsetV (PLT 0x108f44)",
                "+0x04_u16": "SetData_Image_Target_SizeV (PLT 0x1097cc)",
                "+0x06_u16": "SetData_Image_Target_SizeH (PLT 0x10a880)",
                "+0x08_u16": "SetData_Image_SizeV (PLT 0x10c61c)",
                "+0x0a_u16": "SetData_Image_SizeH (PLT 0x10add0)",
                "+0x0c_s16_bpp": "SetData_Image_Sel (PLT 0x109ebc): 2->0, 4->1",
                "+0x10_u32_flags_bits_1_0": "SetData_Image_Out_Target (PLT 0x109b84): flags & 3",
                "+0x10_u32_flags_bit_10": "SetData_Image_Channel (PLT 0x10e39c): (flags >> 10) & 1",
                "+0x10_u32_flags_bit_4_and_bpp4": "SetData_Image_Trans_Type (PLT 0x10b8a0): ((flags & 0x10) != 0 and bpp == 4) -> 1 else 0",
                "const_1": "SetData_Image_Read_Orientation (PLT 0x10e7a4): 1",
                "+0x14_u32": "SetData_Image_Address (PLT 0x109440)",
                "+0x18_u32_profile_id": "unread by 0x6fe064",
            },
            "SetData_Image_Address_callsites": ["0x0028b7cc", "0x0028dcca", "0x0028e716", "0x0028e75c"],
            "GRM_bitmapGetPhysicalAddress": "0x00684e6d",
            "GRM_bitmapWriteLockBits": "0x00684ead",
            "GRM_bitmapWriteUnlockBits": "0x00684ebd",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    gles = _audit_grm_gles(args.repo)
    ma = _audit_grm_ma(args.repo)
    df_obj = _audit_dataflow_and_libobj(args.repo)

    report = {
        "schema_version": 1,
        "status": "offline-original-instruction-grm-contracts-verified",
        "camera_access_performed": False,
        "read_or_write_permission": False,
        "grm_gles": gles,
        "grm_ma": ma,
        **df_obj,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "gles_reg_init_writes": len(gles["register_init_writes"]),
                "gles_ioctl_literals": len(gles["ioctl_literal_commands"]),
                "ma_cache_ops": len(ma["cache_ops"]),
                "df_osd_setters_verified": len(df_obj["dataflowInfraFramework"]["osd_entry_field_layout_runs"]),
                "camera_access_performed": False,
            }
        )
    )


if __name__ == "__main__":
    main()
