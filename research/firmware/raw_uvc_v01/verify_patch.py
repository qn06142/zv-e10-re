"""Offline ARM Unicorn + ELF/ISA + Host Unpacker verification for raw_uvc_v01."""
import hashlib, io, json, re, struct, subprocess, sys, tempfile, zlib
from pathlib import Path
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_ARM
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *

ROOT = Path(r"D:\02_Development_And_Projects\pmca-re")
WORK = Path(__file__).resolve().parent
OUT = ROOT / ".local/outputs/raw-uvc-v01"
sys.path.insert(0, str(WORK))
import unpack_raw_uvc


def check_elf_and_isa():
    print("=== 1. ELF, Export, No-Constructor, Relocation, & ISA checks ===")
    for name in ["raw_capture_v01.so", "raw_uvc_v01.so", "libInfraStreamingUsb.so",
                 "rtos_raw_gate.elf", "prep_saver_stub.elf", "checked_mempatch.elf"]:
        p = OUT / name
        with p.open("rb") as f:
            ef = ELFFile(f)
            assert ef.elfclass == 32 and ef.little_endian and ef["e_machine"] == "EM_ARM"
            if name.endswith(".so") and name != "libInfraStreamingUsb.so":
                for sec_n in [".init_array", ".ctors"]:
                    sec = ef.get_section_by_name(sec_n)
                    assert sec is None or sec["sh_size"] == 0, f"{name} has constructor {sec_n}"
                # Check no unexpected NEON instructions in .text
                txt = ef.get_section_by_name(".text")
                md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
                data = txt.data()
                for ins in md.disasm(data, txt["sh_addr"]):
                    if ins.mnemonic.startswith(("v", "f")) and ins.mnemonic not in ("vcmp",):
                        # Disallow NEON/VFP in library paths for strict Cortex-A5 kernel/soft-ABI parity
                        raise AssertionError(f"Unexpected VFP/NEON {ins.mnemonic} in {name} @ {ins.address:#x}")
            if name == "raw_uvc_v01.so":
                dynsym = ef.get_section_by_name(".dynsym")
                exports = {s.name for s in dynsym.iter_symbols() if s["st_value"] and s["st_info"]["bind"] == "STB_GLOBAL"}
                assert "yuy2_activate" in exports and "yuy2_status" in exports
            if name == "raw_capture_v01.so":
                dynsym = ef.get_section_by_name(".dynsym")
                exports = {s.name for s in dynsym.iter_symbols() if s["st_value"] and s["st_info"]["bind"] == "STB_GLOBAL"}
                for req in ["raw_v01_install", "raw_v01_lazy_entry", "raw_v01_dispatch", "raw_v01_arm", "raw_v01_status"]:
                    assert req in exports, f"Missing {req}"
            if name == "libInfraStreamingUsb.so":
                dyn = ef.get_section_by_name(".dynamic")
                needed = [t.needed for t in dyn.iter_tags() if t.entry.d_tag == "DT_NEEDED"]
                assert "raw_uvc_v01.so" in needed, f"Missing DT_NEEDED in libInfraStreamingUsb.so: {needed}"
    # Check stack usage files if generated
    for su in OUT.glob("*.su"):
        for line in su.read_text().splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                bytes_used = int(parts[1])
                assert bytes_used <= 1024, f"Large stack frame {bytes_used}B in {su.name}: {line}"
    # Check kernel module modinfo matches yc42_chunk fence required by raw_uvc_v01.so
    with (OUT / "usbg_video.ko").open("rb") as f:
        efk = ELFFile(f)
        mi = efk.get_section_by_name(".modinfo")
        assert mi is not None and b"version=yc42_chunk\x00" in mi.data(), "usbg_video.ko missing version=yc42_chunk"
    print("PASS: All ELF, exports, constructor-free, no-NEON/VFP, kmod modinfo, and stack-usage guards passed.")


def test_host_raw_source_and_unpack():
    print("=== 2. Host C raw_source_file + unpack_raw_uvc integration test (2.5MB + 48MiB max) ===")
    gcc = Path(r"C:\msys64\ucrt64\bin\gcc.exe")
    assert gcc.exists(), "Host gcc missing"
    tile = bytes(((i * 37 + (i >> 8) * 13) & 0xFF) for i in range(65536))
    for size_bytes in [2_500_000, 50_331_648]:
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            raw_dir = td / "cap"
            raw_dir.mkdir()
            raw_payload = (tile * ((size_bytes + 65535) // 65536))[:size_bytes]
            pkt = struct.pack("<HHIIBBBBII", 1, 0x0701, 0x20000000, len(raw_payload), 42, 0, 3, 9, 6024, 4040)
            (raw_dir / "request.bin").write_bytes(pkt)
            (raw_dir / "frame.bin").write_bytes(raw_payload)
            (raw_dir / "complete.bin").write_bytes(pkt)

            host_test_c = td / "test_raw_source.c"
            host_test_c.write_text(f"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "raw_source_file.h"
int main(void) {{
    unsigned char hdr[RAW_UVC_HDR_BYTES];
    uint32_t raw_bytes = 0;
    int rc = raw_source_prepare(7, hdr, &raw_bytes);
    if (rc != 0 || raw_bytes != {len(raw_payload)}u) {{ fprintf(stderr, "prepare fail %d %u\\n", rc, raw_bytes); return 1; }}
    unsigned char *chunk = malloc(RAW_UVC_CHUNK_BYTES);
    FILE *out = fopen({json.dumps(str(td / "uvc_stream.bin"))}, "wb");
    for (unsigned off = 0; off < RAW_UVC_FRAME_BYTES; off += RAW_UVC_CHUNK_BYTES) {{
        if (raw_source_read_chunk(hdr, raw_bytes, off, chunk, RAW_UVC_CHUNK_BYTES) != 0) return 2;
        fwrite(chunk, 1, RAW_UVC_CHUNK_BYTES, out);
    }}
    fclose(out);
    raw_source_close();
    return 0;
}}
""", encoding="utf-8")
            exe = td / "test_raw_source.exe"
            subprocess.run([
                str(gcc), "-O2", f"-I{WORK}",
                f"-DRAW_CAPTURE_DIR={json.dumps(str(raw_dir))}",
                str(host_test_c), str(WORK / "raw_source_file.c"), "-o", str(exe)
            ], check=True)
            subprocess.run([str(exe)], check=True)

            cap_blob = (td / "uvc_stream.bin").read_bytes()
            assert len(cap_blob) == 50_380_800
            out_ext = td / "extracted"
            res = unpack_raw_uvc.extract_frames(cap_blob, out_ext)
            assert len(res) == 1
            m = res[0]
            assert m["raw_bytes"] == len(raw_payload)
            assert m["tag"] == 0x0701 and m["sequence"] == 42 and m["c"] == 6024 and m["d"] == 4040
            extracted = Path(m["extracted_file"]).read_bytes()
            assert hashlib.sha256(extracted).digest() == hashlib.sha256(raw_payload).digest()
    print("PASS: Host C chunk reader produced 50,380,800B ZVRAW001 frames (2.5MB & 48MiB max); unpacker matched SHA-256 bit-for-bit.")


def map_elf_in_uc(u: Uc, path: Path, base: int):
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
    return ef


def test_unicorn_lazy_stub_and_capture():
    print("=== 3. Unicorn ARM emulation: CameraOnDemandSaver lazy stub + raw_capture_v01 ===")
    # Execute Keystone lazy stub from OUT/prep_saver_stub.gen.c up to dlopen/dlsym/raw_v01_lazy_entry,
    # then run raw_capture_v01.so!raw_v01_lazy_entry -> raw_v01_install -> raw_v01_dispatch!
    gen_c = (OUT / "prep_saver_stub.gen.c").read_text()
    m = re.search(r"STUB_TEMPLATE\[144\] = \{([^}]+)\};", gen_c, re.S)
    tpl = bytes(int(x.strip(), 16) for x in m.group(1).split(","))

    SAVER = 0x0967e000
    DL = 0x040ba000
    CAP = 0x0a000000
    STACK = 0x0b000000
    STOP = 0x0f000000
    EXT = 0x0c000000
    PHYS = 0x20000000

    u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    map_elf_in_uc(u, ROOT / ".local/dumps/camera_2025/usr/usr/lib/CameraOnDemandSaver.so", SAVER)
    ef_cap = map_elf_in_uc(u, OUT / "raw_capture_v01.so", CAP)
    u.mem_map(DL, 0x4000)
    u.mem_map(STACK, 0x20000)
    u.mem_map(STOP, 0x1000)
    u.mem_map(EXT, 0x10000)
    u.mem_map(PHYS, 0x10000)

    # Mock sensor RAW bytes in PHYS
    mock_raw = bytes(((i * 53 + 7) & 0xFF) for i in range(4096))
    u.mem_write(PHYS + 0x100, mock_raw)

    # Resolve raw_capture_v01.so dynsyms
    dynsym = ef_cap.get_section_by_name(".dynsym")
    cap_syms = {s.name: CAP + s["st_value"] for s in dynsym.iter_symbols() if s.name and s["st_value"]}
    # Relocate GOT/REL inside raw_capture_v01.so
    for rn in [".rel.dyn", ".rel.plt"]:
        sec = ef_cap.get_section_by_name(rn)
        if not sec:
            continue
        for r in sec.iter_relocations():
            sym_idx = r["r_info_sym"]
            rtype = r["r_info_type"]
            sym = dynsym.get_symbol(sym_idx)
            at = CAP + r["r_offset"]
            if rtype == 23:  # R_ARM_RELATIVE
                val = struct.unpack("<I", u.mem_read(at, 4))[0]
                u.mem_write(at, struct.pack("<I", CAP + val))
            elif rtype in (21, 22):  # GLOB_DAT / JUMP_SLOT
                if sym["st_value"]:
                    u.mem_write(at, struct.pack("<I", CAP + sym["st_value"]))
                else:
                    # Point unresolved libc/dl symbols to EXT stubs
                    stub_addr = EXT + 0x100 + sym_idx * 4
                    u.mem_write(at, struct.pack("<I", stub_addr))

    # Populate stub at SAVER + 0x2800 (just like prep_saver_stub.c does)
    stub = bytearray(tpl)
    struct.pack_into("<IIII", stub, 0x34, SAVER, DL + 0x0bb1, DL + 0x0c49, SAVER + 0x1af5)
    u.mem_write(SAVER + 0x2800, bytes(stub))
    u.mem_write(SAVER + 0xa18c, struct.pack("<I", SAVER + 0x2801))

    # Build wire packet at STACK + 0x1000
    wire = STACK + 0x1000
    pkt_bytes = struct.pack("<HHIIBBBBII", 1, 0x0701, PHYS + 0x100, len(mock_raw), 1, 0, 0, 0, 0, 0)
    u.mem_write(wire, pkt_bytes)

    ext_calls = []
    written_files = {}
    open_fds = {}
    next_fd = [10]
    mem_map_va = EXT + 0x8000

    # Map EXT symbol table reverse lookup
    ext_map = {}
    for rn in [".rel.dyn", ".rel.plt"]:
        sec = ef_cap.get_section_by_name(rn)
        if not sec: continue
        for r in sec.iter_relocations():
            sym_idx = r["r_info_sym"]
            sym = dynsym.get_symbol(sym_idx)
            if not sym["st_value"] and r["r_info_type"] in (21, 22):
                ext_map[EXT + 0x100 + sym_idx * 4] = sym.name

    def cstr(addr):
        b = bytearray()
        while True:
            ch = u.mem_read(addr, 1)[0]
            if ch == 0: break
            b.append(ch); addr += 1
        return b.decode("ascii", "replace")

    def hook(uc, pc, size, _):
        # Intercept libdl dlopen/dlsym
        if pc == DL + 0x0bb0:
            path = cstr(uc.reg_read(UC_ARM_REG_R0))
            ext_calls.append(("dlopen", path))
            uc.reg_write(UC_ARM_REG_R0, 0x77770001 if "CameraOnDemandSaver" in path else 0x77770002)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            return
        if pc == DL + 0x0c48:
            sname = cstr(uc.reg_read(UC_ARM_REG_R1))
            ext_calls.append(("dlsym", sname))
            if "fsys_write" in sname:
                uc.reg_write(UC_ARM_REG_R0, SAVER + 0x1af5)
            elif sname == "raw_v01_lazy_entry":
                uc.reg_write(UC_ARM_REG_R0, cap_syms["raw_v01_lazy_entry"])
            else:
                uc.reg_write(UC_ARM_REG_R0, 0)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            return
        name = ext_map.get(pc)
        if name:
            r0 = uc.reg_read(UC_ARM_REG_R0)
            r1 = uc.reg_read(UC_ARM_REG_R1)
            r2 = uc.reg_read(UC_ARM_REG_R2)
            if name == "memcmp":
                a = uc.mem_read(r0, r2); b = uc.mem_read(r1, r2)
                uc.reg_write(UC_ARM_REG_R0, 0 if a == b else 1)
            elif name == "getpagesize":
                uc.reg_write(UC_ARM_REG_R0, 4096)
            elif name == "mprotect":
                uc.reg_write(UC_ARM_REG_R0, 0)
            elif name == "__errno_location":
                uc.reg_write(UC_ARM_REG_R0, EXT + 0x5000)
            elif name == "mkdir":
                uc.reg_write(UC_ARM_REG_R0, 0)
            elif name == "open":
                p = cstr(r0)
                fd = next_fd[0]; next_fd[0] += 1
                open_fds[fd] = p
                if p != "/dev/mem":
                    written_files[p] = bytearray()
                uc.reg_write(UC_ARM_REG_R0, fd)
            elif name == "mmap":
                # arg5 (offset) is at [sp + 4]
                sp = uc.reg_read(UC_ARM_REG_SP)
                pgoff = struct.unpack("<I", uc.mem_read(sp + 4, 4))[0]
                data = uc.mem_read(pgoff, min(r1, 0x8000))
                uc.mem_write(mem_map_va, bytes(data))
                uc.reg_write(UC_ARM_REG_R0, mem_map_va)
            elif name == "write":
                p = open_fds.get(r0)
                if p and p in written_files:
                    written_files[p].extend(uc.mem_read(r1, r2))
                uc.reg_write(UC_ARM_REG_R0, r2)
            elif name in ("fsync", "close", "munmap"):
                uc.reg_write(UC_ARM_REG_R0, 0)
            elif name == "dlopen":
                p = cstr(r0)
                uc.reg_write(UC_ARM_REG_R0, 0x77770001 if "CameraOnDemandSaver" in p else 0x77770002)
            elif name == "dlsym":
                sn = cstr(r1)
                uc.reg_write(UC_ARM_REG_R0, (SAVER + 0x1af5) if "fsys_write" in sn else 0)
            else:
                uc.reg_write(UC_ARM_REG_R0, 0)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    u.hook_add(UC_HOOK_CODE, hook)
    u.reg_write(UC_ARM_REG_SP, STACK + 0x10000)
    u.reg_write(UC_ARM_REG_R0, 0x11223344)
    u.reg_write(UC_ARM_REG_R1, wire)
    u.reg_write(UC_ARM_REG_LR, STOP)

    # Call GOT[+0xa18c] (SAVER + 0x2801)
    u.emu_start(SAVER + 0x2801, STOP, count=200000)
    assert u.reg_read(UC_ARM_REG_PC) == STOP
    assert u.reg_read(UC_ARM_REG_R0) == 1, f"Expected bool 1 return, got {u.reg_read(UC_ARM_REG_R0)}"
    assert u.reg_read(UC_ARM_REG_SP) == STACK + 0x10000
    slot_now = struct.unpack("<I", u.mem_read(SAVER + 0xa18c, 4))[0]
    assert slot_now == cap_syms["raw_v01_dispatch"], f"GOT slot not updated: {slot_now:#x}"
    assert bytes(written_files["/log/raw_capture_v01/request.bin"]) == pkt_bytes
    assert bytes(written_files["/log/raw_capture_v01/frame.bin"]) == mock_raw
    assert bytes(written_files["/log/raw_capture_v01/complete.bin"]) == pkt_bytes
    print("PASS: Lazy stub -> dlopen -> raw_v01_install -> raw_v01_arm -> raw_v01_dispatch captured 4096B RAW bit-for-bit.")


def main():
    check_elf_and_isa()
    test_host_raw_source_and_unpack()
    test_unicorn_lazy_stub_and_capture()
    import verify_uvc_emu
    verify_uvc_emu.run_uvc_carrier_emulation()
    print("ALL OFFLINE VERIFICATIONS PASSED.")


if __name__ == "__main__":
    main()
