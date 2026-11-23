"""Unicorn ARM emulation test for libInfraStreamingUsb persistent cave + raw_uvc_v01.so 82-chunk UVC streaming."""
import hashlib, io, struct, tempfile
from pathlib import Path
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *
import unpack_raw_uvc

ROOT = Path(r"D:\02_Development_And_Projects\pmca-re")
OUT = ROOT / ".local/outputs/raw-uvc-v01"


def _map_and_reloc(u: Uc, path: Path, base: int, ext_base: int, resolve_extra=None):
    raw = path.read_bytes()
    ef = ELFFile(io.BytesIO(raw))
    max_v = 0
    for seg in ef.iter_segments():
        if seg["p_type"] == "PT_LOAD":
            end = (seg["p_vaddr"] + seg["p_memsz"] + 4095) & ~4095
            if end > max_v:
                max_v = end
    u.mem_map(base, max_v)
    for seg in ef.iter_segments():
        if seg["p_type"] == "PT_LOAD":
            off = seg["p_offset"]
            fsz = seg["p_filesz"]
            u.mem_write(base + seg["p_vaddr"], raw[off:off + fsz])

    dynsym = ef.get_section_by_name(".dynsym")
    ext_map = {}
    for rn in [".rel.dyn", ".rel.plt"]:
        sec = ef.get_section_by_name(rn)
        if not sec:
            continue
        for r in sec.iter_relocations():
            sym_idx = r["r_info_sym"]
            rtype = r["r_info_type"]
            sym = dynsym.get_symbol(sym_idx)
            at = base + r["r_offset"]
            if rtype == 23:  # R_ARM_RELATIVE
                val = struct.unpack("<I", u.mem_read(at, 4))[0]
                u.mem_write(at, struct.pack("<I", base + val))
            elif rtype in (21, 22):  # GLOB_DAT / JUMP_SLOT
                if resolve_extra and sym.name in resolve_extra:
                    u.mem_write(at, struct.pack("<I", resolve_extra[sym.name]))
                elif sym["st_value"]:
                    u.mem_write(at, struct.pack("<I", base + sym["st_value"]))
                else:
                    stub_addr = ext_base + 0x100 + sym_idx * 4
                    u.mem_write(at, struct.pack("<I", stub_addr))
                    ext_map[stub_addr] = sym.name
    return ef, dynsym, ext_map


def run_uvc_carrier_emulation():
    print("=== 4. Unicorn ARM emulation: persistent cave -> raw_uvc_v01 -> 82-chunk UVC -> unpack_raw_uvc ===")
    SB = 0x05000000
    CB = 0x06000000
    UVC = 0x08000000
    EXT = 0x0c000000
    HEAP = 0x0d000000
    MMAP_ALLOC = 0x0e000000
    PIX_VA = 0x0e800000
    STACK = 0x0f000000
    STOP = 0x0ff00000
    PIX_PHYS = 0x31000000

    u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    u.mem_map(EXT, 0x20000)
    u.mem_map(HEAP, 0x200000)
    u.mem_map(MMAP_ALLOC, 0x1000000)
    u.mem_map(STACK, 0x40000)
    u.mem_map(STOP, 0x1000)

    ef_uvc, uvc_dynsym, ext_map = _map_and_reloc(u, OUT / "raw_uvc_v01.so", UVC, EXT)
    uvc_syms = {s.name: UVC + s["st_value"] for s in uvc_dynsym.iter_symbols() if s.name and s["st_value"]}
    _map_and_reloc(u, OUT / "libInfraStreamingUsb.so", SB, EXT + 0x8000, {"yuy2_activate": uvc_syms["yuy2_activate"]})
    _map_and_reloc(u, ROOT / ".local/dumps/camera_2025/usr/usr/lib/libInfraUsbCmn.so", CB, EXT + 0xc000)

    raw_payload = bytes(((i * 73 + (i >> 8) * 19 + 5) & 0xFF) for i in range(65536))
    pkt_bytes = struct.pack("<HHIIBBBBII", 1, 0x0701, 0x20000000, len(raw_payload), 9, 0, 1, 2, 6024, 4040)

    vfiles = {
        "/proc/self/maps": f"{SB:08x}-{SB+0x40000:08x} r-xp 00000000 00:00 0 /usr/lib/libInfraStreamingUsb.so\n"
                           f"{CB:08x}-{CB+0x40000:08x} r-xp 00000000 00:00 0 /usr/lib/libInfraUsbCmn.so\n".encode(),
        "/proc/udm/dmm_units": b"0001 050e 0001 0000 0000 0000 0000 0000 30000000 00200000\n",
        "/sys/module/usbg_video/version": b"yc42_chunk\n",
        "/dev/stream": b"",
        "/log/raw_capture_v01/request.bin": pkt_bytes,
        "/log/raw_capture_v01/complete.bin": pkt_bytes,
        "/log/raw_capture_v01/frame.bin": raw_payload,
    }
    log_lines = bytearray()
    fds = {}
    next_fd = [20]
    heap_ptr = [HEAP + 0x10000]
    mmap_ptr = [MMAP_ALLOC]
    handle_val = 0x0101
    SM_OBJ = HEAP + 0x1000
    SELF_OBJ = HEAP + 0x2000
    STATE_OBJ = HEAP + 0x3000
    MSG_OBJ = HEAP + 0x3100
    INFO_OBJ = HEAP + 0x4000
    u.mem_write(SM_OBJ + 0x34, struct.pack("<I", SELF_OBJ))
    u.mem_write(MSG_OBJ + 4, struct.pack("<I", 0x99))

    sony_dlsyms = {}
    sony_names = [
        "_ZN14VideoEsManager18alloc_video_memoryEjPtPjS1_",
        "_ZN14VideoEsManager20dealloc_video_memoryEPt",
        "_Z16WaitVideoReadCmpv",
        "_Z17UpdateVideoBufEvt22StreamingVideoDataInfo",
        "_ZN14VideoEsManager27judge_notify_start_stop_evtEPNS_14VIDEO_MGR_INFOEb",
        "_ZN19CUsbGadgetStreaming13SendProbeInfoEP29usbg_video_probe_commit_ctrls",
        "_ZN19CUsbGadgetStreaming14SendCommitInfoEP29usbg_video_probe_commit_ctrls",
        "_ZN3UFW3Sem4LockEv",
        "_ZN3UFW3Sem6UnlockEv",
        "SendEvtStreamingMain",
        "_Z11sendCompMsgjP16ST_MSG_ASYNC_CMP",
        "_ZN12StateMachine5State15getStateMachineEv",
        "_ZN12StateMachine11changeStateEPNS_5StateE",
    ]
    for i, nm in enumerate(sony_names):
        sony_dlsyms[nm] = EXT + 0x4000 + i * 4
    sony_rev = {v: k for k, v in sony_dlsyms.items()}

    emitted_chunks = []
    judge_calls = []
    stop_pc_override = [None]

    def cstr(addr):
        b = bytearray()
        while True:
            ch = u.mem_read(addr, 1)[0]
            if ch == 0:
                break
            b.append(ch)
            addr += 1
        return b.decode("latin1")

    def ret_val(uc, v):
        uc.reg_write(UC_ARM_REG_R0, v & 0xffffffff)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def hook(uc, pc, size, _):
        if stop_pc_override[0] is not None and pc == stop_pc_override[0]:
            uc.reg_write(UC_ARM_REG_PC, STOP)
            return
        if pc == SB + 0x7aa8 + 10:
            # Unwind stolen prologue: push.w {r4..r8, lr}; sub sp, #0x48
            sp = uc.reg_read(UC_ARM_REG_SP) + 0x48
            lr_saved = struct.unpack("<I", uc.mem_read(sp + 20, 4))[0]
            uc.reg_write(UC_ARM_REG_SP, sp + 24)
            uc.reg_write(UC_ARM_REG_R0, 0)
            uc.reg_write(UC_ARM_REG_PC, lr_saved)
            return
        if pc == SB + 0x903e + 10:
            # Unwind stolen prologue: push {r4..r7, lr}; sub sp, #0xc
            sp = uc.reg_read(UC_ARM_REG_SP) + 0x0c
            lr_saved = struct.unpack("<I", uc.mem_read(sp + 16, 4))[0]
            uc.reg_write(UC_ARM_REG_SP, sp + 20)
            uc.reg_write(UC_ARM_REG_R0, 0)
            uc.reg_write(UC_ARM_REG_PC, lr_saved)
            return

        if pc in sony_rev:
            nm = sony_rev[pc]
            r0 = uc.reg_read(UC_ARM_REG_R0)
            r1 = uc.reg_read(UC_ARM_REG_R1)
            r2 = uc.reg_read(UC_ARM_REG_R2)
            r3 = uc.reg_read(UC_ARM_REG_R3)
            sp = uc.reg_read(UC_ARM_REG_SP)
            if nm == "_ZN14VideoEsManager18alloc_video_memoryEjPtPjS1_":
                cap_ptr = struct.unpack("<I", uc.mem_read(sp, 4))[0]
                uc.mem_write(r2, struct.pack("<H", handle_val))
                uc.mem_write(r3, struct.pack("<I", PIX_PHYS))
                uc.mem_write(cap_ptr, struct.pack("<I", 0x100000))
                ret_val(uc, 0)
            elif nm == "_ZN12StateMachine5State15getStateMachineEv":
                ret_val(uc, SM_OBJ)
            elif nm == "_Z17UpdateVideoBufEvt22StreamingVideoDataInfo":
                assert r1 == PIX_PHYS, f"Bad physical DMA addr {r1:#x}"
                sz = r0 & 0x0fffffff
                emitted_chunks.append((r0, bytes(uc.mem_read(PIX_VA, sz))))
                ret_val(uc, 0)
            elif nm == "_ZN14VideoEsManager27judge_notify_start_stop_evtEPNS_14VIDEO_MGR_INFOEb":
                judge_calls.append(r2)
                ret_val(uc, 0)
            else:
                ret_val(uc, 0)
            return

        name = ext_map.get(pc)
        if not name:
            return
        r0 = uc.reg_read(UC_ARM_REG_R0)
        r1 = uc.reg_read(UC_ARM_REG_R1)
        r2 = uc.reg_read(UC_ARM_REG_R2)
        r3 = uc.reg_read(UC_ARM_REG_R3)
        sp = uc.reg_read(UC_ARM_REG_SP)

        if name == "malloc":
            addr = (heap_ptr[0] + 7) & ~7
            heap_ptr[0] = addr + max(16, r0)
            ret_val(uc, addr)
        elif name == "free":
            ret_val(uc, 0)
        elif name == "memcpy":
            uc.mem_write(r0, bytes(uc.mem_read(r1, r2)))
            ret_val(uc, r0)
        elif name == "memset":
            uc.mem_write(r0, bytes([r1 & 0xff]) * r2)
            ret_val(uc, r0)
        elif name == "memcmp":
            a = uc.mem_read(r0, r2)
            b = uc.mem_read(r1, r2)
            ret_val(uc, 0 if a == b else 1)
        elif name == "strchr":
            s = r0
            ch = r1 & 0xff
            while True:
                b = uc.mem_read(s, 1)[0]
                if b == ch:
                    ret_val(uc, s)
                    break
                if b == 0:
                    ret_val(uc, 0)
                    break
                s += 1
        elif name == "strstr":
            hay = cstr(r0)
            nd = cstr(r1)
            idx = hay.find(nd)
            ret_val(uc, (r0 + idx) if idx >= 0 else 0)
        elif name == "snprintf":
            fmt = cstr(r2)
            a0, a1, a2 = struct.unpack("<III", uc.mem_read(sp, 12))
            if "%s" in fmt:
                txt = (fmt % (cstr(r3), a0, a1, a2))[:max(0, r1 - 1)]
            else:
                nargs = fmt.count("%")
                vals = (r3, a0, a1, a2)[:nargs]
                txt = (fmt % vals)[:max(0, r1 - 1)]
            uc.mem_write(r0, txt.encode("latin1") + b"\x00")
            ret_val(uc, len(txt))
        elif name == "sscanf":
            line = cstr(r0)
            fmt = cstr(r1)
            if fmt.strip() == "%x":
                parts = line.split("-", 1)[0].strip()
                try:
                    val = int(parts, 16)
                    uc.mem_write(r2, struct.pack("<I", val))
                    ret_val(uc, 1)
                except ValueError:
                    ret_val(uc, 0)
            else:
                cols = line.split()
                if len(cols) == 10:
                    ptrs = [r2, r3] + list(struct.unpack("<8I", uc.mem_read(sp, 32)))
                    for p, c in zip(ptrs, cols):
                        uc.mem_write(p, struct.pack("<I", int(c, 16)))
                    ret_val(uc, 10)
                else:
                    ret_val(uc, 0)
        elif name == "open":
            p = cstr(r0)
            if p == "/log/raw_uvc_v01/runtime.log":
                fd = next_fd[0]; next_fd[0] += 1
                fds[fd] = (p, 0)
                ret_val(uc, fd)
            elif p in vfiles:
                fd = next_fd[0]; next_fd[0] += 1
                fds[fd] = (p, 0)
                ret_val(uc, fd)
            else:
                ret_val(uc, -1)
        elif name == "close":
            fds.pop(r0, None)
            ret_val(uc, 0)
        elif name == "read":
            if r0 not in fds:
                ret_val(uc, -1); return
            p, off = fds[r0]
            data = vfiles[p]
            chunk = data[off:off + r2]
            if chunk:
                uc.mem_write(r1, chunk)
                fds[r0] = (p, off + len(chunk))
            ret_val(uc, len(chunk))
        elif name == "lseek":
            if r0 not in fds:
                ret_val(uc, -1); return
            p, off = fds[r0]
            data = vfiles[p]
            if r2 == 0:
                noff = r1
            elif r2 == 1:
                noff = off + r1
            elif r2 == 2:
                noff = len(data) + r1
            else:
                ret_val(uc, -1); return
            fds[r0] = (p, noff)
            ret_val(uc, noff)
        elif name == "write":
            p, _ = fds.get(r0, ("", 0))
            if p == "/log/raw_uvc_v01/runtime.log":
                log_lines.extend(uc.mem_read(r1, r2))
            ret_val(uc, r2)
        elif name == "mmap":
            fd, pgoff = struct.unpack("<ii", uc.mem_read(sp, 8))
            if fd == -1:
                va = mmap_ptr[0]
                mmap_ptr[0] += (r1 + 4095) & ~4095
                ret_val(uc, va)
            else:
                assert (pgoff & 0xffffffff) == (PIX_PHYS & ~4095)
                ret_val(uc, PIX_VA)
        elif name in ("munmap", "mprotect", "sched_yield"):
            ret_val(uc, 0)
        elif name == "__errno_location":
            ret_val(uc, HEAP + 0x500)
        elif name == "syscall":
            if r0 == 263:  # clock_gettime
                uc.mem_write(r2, struct.pack("<II", 1, 0))
            ret_val(uc, 0)
        elif name == "dlopen":
            p = cstr(r0)
            if "raw_uvc_v01" in p:
                ret_val(uc, 0x88880001)
            elif "libInfraStreamingUsb" in p:
                ret_val(uc, 0x88880002)
            elif "libInfraUsbCmn" in p:
                ret_val(uc, 0x88880003)
            else:
                ret_val(uc, 0)
        elif name == "dlsym":
            ret_val(uc, sony_dlsyms.get(cstr(r1), 0))
        else:
            raise RuntimeError(f"Unhandled EXT call: {name}")

    u.hook_add(UC_HOOK_CODE, hook)

    # Step A: Enter persistent libInfraStreamingUsb cave entry SB + 0x8d01 -> runs yuy2_activate -> install()
    stop_pc_override[0] = SB + 0x8d0c
    u.reg_write(UC_ARM_REG_SP, STACK + 0x20000)
    u.reg_write(UC_ARM_REG_LR, STOP)
    u.emu_start(SB + 0x8d01, STOP, count=500000)
    stop_pc_override[0] = None

    # Check yuy2_status() == 1
    u.reg_write(UC_ARM_REG_SP, STACK + 0x20000)
    u.reg_write(UC_ARM_REG_LR, STOP)
    u.emu_start(uvc_syms["yuy2_status"], STOP, count=10000)
    assert u.reg_read(UC_ARM_REG_R0) == 1, "yuy2_status() != 1 after persistent activation"

    # Check patched binary locations inside CB and SB
    assert struct.unpack("<H", u.mem_read(CB + 0xcd7c, 2))[0] == 0x2305, "SuperSpeed 0x2305 not patched"
    assert struct.unpack("<I", u.mem_read(CB + 0x1df28, 4))[0] == 0x105, "DID60 mask not 0x105"
    assert struct.unpack("<I", u.mem_read(CB + 0x1e178, 4))[0] == 0x105, "DID61 mask not 0x105"
    assert u.mem_read(SB + 0x8e14, 4) == b"\x00\x20\x70\x47", "no_codec stub not installed"
    for off in (0x1cab8, 0x1cdb0, 0x1cb30, 0x1ce28):
        tbl_len, tbl_ptr = struct.unpack("<II", u.mem_read(CB + off, 8))
        assert tbl_len == 77
        desc = bytes(u.mem_read(tbl_ptr, 77))
        w, h = struct.unpack_from("<HH", desc, 14 + 27 + 5)
        max_fb, iv = struct.unpack_from("<II", desc, 14 + 27 + 17)
        assert (w, h, max_fb, iv) == (6144, 4100, 50380800, 2000000), f"Bad descriptor {(w, h, max_fb, iv)}"

    # Step B: connect_hook via SB + 0x7aa9
    u.reg_write(UC_ARM_REG_SP, STACK + 0x20000)
    u.reg_write(UC_ARM_REG_R0, STATE_OBJ)
    u.reg_write(UC_ARM_REG_R1, MSG_OBJ)
    u.reg_write(UC_ARM_REG_LR, STOP)
    u.emu_start(SB + 0x7aa9, STOP, count=200000)
    assert u.reg_read(UC_ARM_REG_R0) == 0, f"connect_hook returned {u.reg_read(UC_ARM_REG_R0)}"

    # Step C: start_hook via SB + 0x903f
    u.reg_write(UC_ARM_REG_SP, STACK + 0x20000)
    u.reg_write(UC_ARM_REG_R0, SELF_OBJ)
    u.reg_write(UC_ARM_REG_LR, STOP)
    u.emu_start(SB + 0x903f, STOP, count=200000)
    assert u.reg_read(UC_ARM_REG_R0) == 0, f"start_hook returned {u.reg_read(UC_ARM_REG_R0)}"

    # Step D: Run produce() 82 times via SB + 0x9619
    for idx in range(82):
        u.reg_write(UC_ARM_REG_SP, STACK + 0x20000)
        u.reg_write(UC_ARM_REG_R0, SELF_OBJ)
        u.reg_write(UC_ARM_REG_R1, INFO_OBJ)
        u.reg_write(UC_ARM_REG_LR, STOP)
        u.emu_start(SB + 0x9619, STOP, count=20000000)
        assert u.reg_read(UC_ARM_REG_PC) == STOP, f"produce() chunk {idx} hit instruction limit at pc={u.reg_read(UC_ARM_REG_PC):#x}"
        rc = u.reg_read(UC_ARM_REG_R0)
        assert rc == 0, f"produce() chunk {idx} failed rc={rc}; logs:\n{log_lines.decode('latin1')}"

    assert len(emitted_chunks) == 82
    assert judge_calls == [1], f"Unexpected judge calls: {judge_calls}"
    full_frame = bytearray()
    for idx, (packed, payload) in enumerate(emitted_chunks):
        expect_more = 0x80000000 if idx < 81 else 0
        expect_packed = 614400 | 0x20000000 | 0x40000000 | expect_more
        assert packed == expect_packed, f"Chunk {idx} header {packed:#x} != {expect_packed:#x}"
        assert len(payload) == 614400
        full_frame.extend(payload)
    assert len(full_frame) == 50_380_800

    # Step E: Unpack with host unpack_raw_uvc and check SHA-256 identity
    with tempfile.TemporaryDirectory() as td:
        res = unpack_raw_uvc.extract_frames(bytes(full_frame), Path(td))
        assert len(res) == 1
        m = res[0]
        assert (m["raw_bytes"], m["tag"], m["sequence"], m["c"], m["d"]) == (65536, 0x0701, 9, 6024, 4040)
        got = Path(m["extracted_file"]).read_bytes()
        assert hashlib.sha256(got).digest() == hashlib.sha256(raw_payload).digest()

    print("PASS: ARM Unicorn full UVC flow (persistent cave -> SuperSpeed/6144x4100 patch -> 82x614400B produce -> unpack) matched SHA-256 bit-for-bit.")
