"""Build and package the Sony ZV-E10 Route-1 full-size Bayer RAW -> USB UVC patch."""
from pathlib import Path
import argparse, hashlib, io, json, re, shutil, struct, subprocess
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from elftools.elf.elffile import ELFFile
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB

ROOT = Path(r"D:\02_Development_And_Projects\pmca-re")
WORK = Path(__file__).resolve().parent
OUT = ROOT / ".local/outputs/raw-uvc-v01"
CC = Path(r"C:\msys64\ucrt64\bin\arm-none-eabi-gcc.exe")

STREAM_BASE = ROOT / ".local/dumps/staged/uvc/encoder-workspace-fix/candidate-1080p/libInfraStreamingUsb.so"
CMN_BASE = ROOT / ".local/dumps/camera_2025/usr/usr/lib/libInfraUsbCmn.so"
SAVER_BASE = ROOT / ".local/dumps/camera_2025/usr/usr/lib/CameraOnDemandSaver.so"
DMM_CFG = ROOT / ".local/dumps/camera_2025/usr/setting/DmmConfig.bin"
KMOD_SRC = ROOT / ".local/outputs/hd-v43/usbg_video.ko"
PATCH_RECIPE = ROOT / ".local/outputs/yuy2-640-v2/deployment/live-recipe"


def check_baselines():
    cmn = CMN_BASE.read_bytes()
    stream = STREAM_BASE.read_bytes()
    saver = SAVER_BASE.read_bytes()
    cfg = DMM_CFG.read_bytes()
    kmod = KMOD_SRC.read_bytes()
    assert hashlib.md5(cmn).hexdigest() == "31308976206a837f6f5c571992d2b499"
    assert hashlib.md5(stream).hexdigest() == "19461091c07aa6900829defb0060fcd6"
    assert hashlib.md5(saver).hexdigest() == "845879287112a8e3d3228897a3e23b72"
    assert hashlib.md5(cfg).hexdigest() == "9f197ff9b300e49ab531b6f9e794253e"
    assert hashlib.md5(kmod).hexdigest() == "9ded6930932e7db541247c4b158b93fc"
    assert struct.unpack_from("<4I", cfg, 0x11c24) == (0x276, 0, 0x333, 0xffffffff)
    assert struct.unpack_from("<5I", cfg, 0x2e20) == (0x333, 0x320000, 0x10f, 0, 7)
    return cmn, stream


def build_persistent_stream(stream_data: bytes, dependency: str, symbol: str):
    CAVE = 0x90c0
    CAVE_SIZE = 380
    ENTRY = 0x8d00
    align = lambda v, a=4: (v + a - 1) & ~(a - 1)
    e = ELFFile(io.BytesIO(stream_data))
    out = bytearray(stream_data)
    shoff = e["e_shoff"]
    phoff = e["e_phoff"]
    sections = {s.name: (i, s) for i, s in enumerate(e.iter_sections())}
    rw_index, rw = next((i, p) for i, p in enumerate(e.iter_segments())
                        if p["p_type"] == "PT_LOAD" and p["p_flags"] == 6)
    delta = rw["p_vaddr"] - rw["p_offset"]
    bss_lo = rw["p_offset"] + rw["p_filesz"]
    bss_hi = rw["p_offset"] + rw["p_memsz"]
    for name, (index, s) in sections.items():
        if s["sh_type"] == "SHT_NOBITS" or not s["sh_size"]:
            continue
        lo, hi = s["sh_offset"], s["sh_offset"] + s["sh_size"]
        if lo < bss_hi and bss_lo < hi:
            assert not (s["sh_flags"] & 2)
            pos = align(len(out), max(1, s["sh_addralign"]))
            out.extend(b"\0" * (pos - len(out)))
            out.extend(s.data())
            struct.pack_into("<I", out, shoff + index * 40 + 16, pos)
    out[bss_lo:bss_hi] = b"\0" * (bss_hi - bss_lo)

    def append(blob, boundary=4):
        pos = align(len(out), boundary)
        out.extend(b"\0" * (pos - len(out)))
        out.extend(blob)
        return pos, pos + delta

    def replace_section(name, blob, boundary=4):
        index, _ = sections[name]
        pos, va = append(blob, boundary)
        struct.pack_into("<III", out, shoff + index * 40 + 12, va, pos, len(blob))
        return va

    old_strings = e.get_section_by_name(".dynstr").data()
    sym = e.get_section_by_name(".dynsym")
    needed_offset = len(old_strings)
    symbol_offset = needed_offset + len(dependency) + 1
    strings = old_strings + dependency.encode() + b"\0" + symbol.encode() + b"\0"
    string_va = replace_section(".dynstr", strings)
    old_syms = sym.data()
    index = len(old_syms) // 16
    sym_va = replace_section(".dynsym", old_syms + struct.pack("<IIIBBH", symbol_offset, 0, 0, 0x12, 0, 0))
    version_va = replace_section(".gnu.version", e.get_section_by_name(".gnu.version").data() + struct.pack("<H", 1), 2)
    _, slot_va = append(b"\0" * 4)
    rels = e.get_section_by_name(".rel.dyn").data() + struct.pack("<II", slot_va, (index << 8) | 21)
    rel_va = replace_section(".rel.dyn", rels)

    tags = []
    overrides = {5: string_va, 6: sym_va, 10: len(strings), 17: rel_va, 18: len(rels), 0x6ffffff0: version_va}
    dyn_data = e.get_section_by_name(".dynamic").data()
    for tag in e.get_section_by_name(".dynamic").iter_tags():
        tn = struct.unpack_from("<I", dyn_data, len(tags) * 8)[0]
        if tn == 0:
            break
        tags.append((tn, overrides.get(tn, tag.entry.d_val)))
    tags.extend([(1, needed_offset), (0, 0)])
    dyn_blob = b"".join(struct.pack("<II", a, b) for a, b in tags)
    dyn_va = replace_section(".dynamic", dyn_blob)
    dyn_index = next(i for i, p in enumerate(e.iter_segments()) if p["p_type"] == "PT_DYNAMIC")
    struct.pack_into("<IIIIII", out, phoff + dyn_index * 32 + 4, dyn_va - delta, dyn_va, dyn_va, len(dyn_blob), len(dyn_blob), 6)
    sz = len(out) - rw["p_offset"]
    struct.pack_into("<II", out, phoff + rw_index * 32 + 16, sz, sz)

    asm = f"""
    entry:
        push {{r0,r1,r2,r3,r4,r5,r6,lr}}
        adr.w r2,entry
        ldr r3,slot_delta
        add r3,r2
        ldr r3,[r3]
        blx r3
        cmp r0,#1
        bne failed
        pop.w {{r0,r1,r2,r3,r4,r5,r6,lr}}
        push {{r3,r4,r5,r6,r7,lr}}
        movs r1,#0
        mov r4,r0
        add r7,sp,#0
        movs r0,#4
        mov r2,r1
        b.w {ENTRY+12:#x}
    failed:
        pop.w {{r0,r1,r2,r3,r4,r5,r6,lr}}
        movs r0,#4
        bx lr
        .align 2
    slot_delta: .word {slot_va - CAVE}
    """
    code = bytes(Ks(KS_ARCH_ARM, KS_MODE_THUMB).asm(asm, addr=CAVE)[0])
    assert len(code) <= CAVE_SIZE
    code += b"\x00\xbf" * ((CAVE_SIZE - len(code)) // 2)
    out[CAVE:CAVE + CAVE_SIZE] = code
    branch = bytes(Ks(KS_ARCH_ARM, KS_MODE_THUMB).asm(f"b.w {CAVE:#x}", addr=ENTRY)[0])
    out[ENTRY:ENTRY + 12] = branch + b"\x00\xbf" * 4
    return bytes(out)


def verify_stub_bytes():
    ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
    so_path = b"/log/raw_uvc_v01/raw_capture_v01.so\0"
    sym_name = b"raw_v01_lazy_entry\0"
    asm = f"""
        push {{r0,r1,r2,r3,r4,r5,r6,lr}}
        mov r4, r0
        mov r5, r1
        adr r0, so_str
        movs r1, #6
        ldr r3, dlopen_ptr
        blx r3
        cbz r0, fallback
        adr r1, sym_str
        ldr r3, dlsym_ptr
        blx r3
        cbz r0, fallback
        mov r3, r0
        ldr r0, base_ptr
        mov r1, r4
        mov r2, r5
        blx r3
        add sp, #16
        pop {{r4,r5,r6,pc}}
    fallback:
        mov r0, r4
        mov r1, r5
        ldr r3, orig_ptr
        blx r3
        add sp, #16
        pop {{r4,r5,r6,pc}}
        .align 2
    base_ptr:   .word 0
    dlopen_ptr: .word 0
    dlsym_ptr:  .word 0
    orig_ptr:   .word 0
    so_str:     .byte {','.join(str(b) for b in so_path)}
    sym_str:    .byte {','.join(str(b) for b in sym_name)}
    """
    enc, _ = ks.asm(asm, 0)
    enc = bytes(enc)
    assert len(enc) <= 144, f"Stub too big: {len(enc)}"
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    # Check offsets of the 4 literal words inside assembled blob
    print("Keystone verified lazy stub length:", len(enc))
    for i in md.disasm(enc[:0x3c], 0):
        print(f"  +{i.address:02x}: {i.mnemonic:8s} {i.op_str}")
    return enc


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cmn, stream = check_baselines()
    stub_bytes = verify_stub_bytes()

    # Patch prep_saver_stub.c literal offsets cleanly from Keystone assembly
    prep_src = (WORK / "prep_saver_stub.c").read_text(encoding="utf-8")
    # Locate the zero-placeholder offsets (base_ptr, dlopen_ptr, dlsym_ptr, orig_ptr) in enc
    base_lit_off = len(stub_bytes) - (len(b"/log/raw_uvc_v01/raw_capture_v01.so\0") + len(b"raw_v01_lazy_entry\0")) - 16
    so_off = base_lit_off + 16
    sym_off = so_off + len(b"/log/raw_uvc_v01/raw_capture_v01.so\0")
    print(f"Stub layout: literals={base_lit_off:#x} so={so_off:#x} sym={sym_off:#x}")

    # Regenerate prep_saver_stub.c template cleanly from Keystone bytes if needed
    # Wait: let's inject exact Keystone-verified 144B template into OUT/prep_saver_stub.gen.c!
    tpl = bytearray(144)
    tpl[:len(stub_bytes)] = stub_bytes
    gen_prep = prep_src
    # Update template array & literal offsets dynamically
    arr_str = ", ".join(f"0x{b:02x}" for b in tpl)
    gen_prep = re.sub(
        r"/\* STUB_TEMPLATE_START \*/.*?/\* STUB_TEMPLATE_END \*/",
        f"/* STUB_TEMPLATE_START */\nstatic const u8 STUB_TEMPLATE[144] = {{{arr_str}}};\n/* STUB_TEMPLATE_END */",
        gen_prep,
        flags=re.S,
    )
    assert "STUB_TEMPLATE[144] = {0x" in gen_prep, "STUB_TEMPLATE replacement failed"
    gen_prep = gen_prep.replace("memcpy(stub, STUB_TEMPLATE, 0x78u);",
                                f"memcpy(stub, STUB_TEMPLATE, {len(stub_bytes)}u);")
    gen_prep = gen_prep.replace("w32(stub + 0x44, sb);", f"w32(stub + {base_lit_off:#x}, sb);")
    gen_prep = gen_prep.replace("w32(stub + 0x48, dl + DLOPEN_OFF);", f"w32(stub + {base_lit_off+4:#x}, dl + DLOPEN_OFF);")
    gen_prep = gen_prep.replace("w32(stub + 0x4c, dl + DLSYM_OFF);", f"w32(stub + {base_lit_off+8:#x}, dl + DLSYM_OFF);")
    gen_prep = gen_prep.replace("w32(stub + 0x50, sb + FN_OFF);", f"w32(stub + {base_lit_off+12:#x}, sb + FN_OFF);")
    gen_prep = gen_prep.replace('memcpy(stub + 0x78, "raw_v01_lazy_entry\\0", 19);',
                                "/* sym string already in template */")
    (OUT / "prep_saver_stub.gen.c").write_text(gen_prep, encoding="utf-8")

    # Prepare raw_uvc_carrier.gen.c with extracted binary guards
    carrier_src = (WORK / "raw_uvc_carrier.c").read_text(encoding="utf-8")
    for name, data in [
        ("path_guard", stream[0x8e14:0x8e1e]),
        ("data_guard", stream[0x9618:0x9622]),
        ("ctrl_guard", cmn[0x12064:0x1206e]),
    ]:
        carrier_src = re.sub(
            r"(static const u8 " + name + r"\[10\]=)\{[^}]+\}",
            lambda m: m[1] + "{" + ",".join(hex(b) for b in data) + "}",
            carrier_src,
        )
    guards = []
    for off in [0x7aa8, 0x903e, 0x8f9c, 0x8dbe, 0x894c, 0x83c8]:
        data = stream[off:off + 10]
        ins = list(Cs(CS_ARCH_ARM, CS_MODE_THUMB).disasm(data, off))
        assert sum(i.size for i in ins) == 10
        assert not any("pc" in i.op_str or i.mnemonic.startswith(("b", "cb", "it")) for i in ins)
        guards.append("{" + ",".join(hex(x) for x in data) + "}")
    carrier_src = carrier_src.replace("EXTRA_GUARDS", ",".join(guards))
    (OUT / "raw_uvc_carrier.gen.c").write_text(carrier_src, encoding="utf-8")

    common = [
        "-mcpu=cortex-a5", "-marm", "-mfloat-abi=soft", "-O2",
        "-fno-builtin", "-fno-stack-protector", "-fstack-usage", "-nostdlib",
        f"-L{ROOT}/.local/build_sysroot/lib", f"-Wl,-rpath-link,{ROOT}/.local/build_sysroot/lib",
    ]
    start_s = str(PATCH_RECIPE / "arm_linux_start.S")

    # 1. Build raw_capture_v01.so
    subprocess.run([
        str(CC), "-std=c11", *common, "-fPIC", "-fvisibility=hidden", "-shared",
        "-Wl,--hash-style=sysv,-soname,raw_capture_v01.so,--no-undefined",
        "-o", str(OUT / "raw_capture_v01.so"),
        str(WORK / "raw_capture/capture.c"),
        str(WORK / "raw_capture/runtime.c"),
        str(WORK / "raw_capture/install.c"),
        "-l:libc.so.6", "-l:libdl.so.2", "-lgcc",
    ], check=True)

    # 2. Build raw_uvc_v01.so
    v43_inc = ROOT / "research/firmware/yuy2_transport_v43_usb3_hd/recipe"
    subprocess.run([
        str(CC), *common, "-fPIC", "-fvisibility=hidden", "-shared",
        "-Wl,--hash-style=sysv,-soname,raw_uvc_v01.so,--no-undefined",
        f"-I{WORK}", f"-I{v43_inc}",
        "-DRAW_FRAME_CONVERSION_ONLY", "-DRAW_LIVE_TARGET_ARM",
        "-o", str(OUT / "raw_uvc_v01.so"),
        str(OUT / "raw_uvc_carrier.gen.c"),
        str(WORK / "raw_source_file.c"),
        "-l:libc.so.6", "-l:libdl.so.2", "-l:libpthread-2.11.2.so", "-lgcc",
    ], check=True)

    # 3. Build rtos_raw_gate.elf, prep_saver_stub.elf, checked_mempatch.elf
    for exe_name, src_path in [
        ("rtos_raw_gate.elf", WORK / "rtos_raw_gate.c"),
        ("prep_saver_stub.elf", OUT / "prep_saver_stub.gen.c"),
        ("checked_mempatch.elf", PATCH_RECIPE / "checked_mempatch.c"),
    ]:
        subprocess.run([
            str(CC), *common,
            "-Wl,--dynamic-linker=/lib/ld-linux.so.3,-e,_start,--hash-style=sysv",
            "-o", str(OUT / exe_name),
            str(src_path), start_s,
            "-l:libc.so.6", "-lgcc",
        ], check=True)

    # 4. Build persistent libInfraStreamingUsb.so depending on raw_uvc_v01.so
    patched_stream = build_persistent_stream(stream, "raw_uvc_v01.so", "yuy2_activate")
    (OUT / "libInfraStreamingUsb.so").write_bytes(patched_stream)
    shutil.copy2(KMOD_SRC, OUT / "usbg_video.ko")
    shutil.copy2(WORK / "unpack_raw_uvc.py", OUT / "unpack_raw_uvc.py")

    # 5. Write deployment scripts
    artifacts = [
        "raw_capture_v01.so", "raw_uvc_v01.so", "rtos_raw_gate.elf",
        "prep_saver_stub.elf", "checked_mempatch.elf", "libInfraStreamingUsb.so", "usbg_video.ko"
    ]
    hashes = {f: hashlib.md5((OUT / f).read_bytes()).hexdigest() for f in artifacts}

    arm_script = f"""#!/bin/sh
set -eu
BB=/bin/busybox
D=/log/raw_uvc_v01
hash() {{ $BB md5sum "$1" | $BB cut -d ' ' -f 1; }}
[ "$(hash "$D/raw_capture_v01.so")" = "{hashes['raw_capture_v01.so']}" ]
[ "$(hash "$D/rtos_raw_gate.elf")" = "{hashes['rtos_raw_gate.elf']}" ]
[ "$(hash "$D/prep_saver_stub.elf")" = "{hashes['prep_saver_stub.elf']}" ]
[ "$(hash "$D/checked_mempatch.elf")" = "{hashes['checked_mempatch.elf']}" ]
$BB chmod 755 "$D/rtos_raw_gate.elf" "$D/prep_saver_stub.elf" "$D/checked_mempatch.elf"

P=$($BB pidof im.elf)
[ -n "$P" ]
$BB mkdir -p "$D/blobs"

# Verify live CameraOnDemandSaver.so + generate exact ASLR-safe stub/slot blobs
LINE=$("$D/prep_saver_stub.elf" "$P" "$D/blobs")
echo "$LINE"
STUB_AT=$(echo "$LINE" | $BB sed -n 's/.*STUB_AT=\\([0-9a-fA-F]*\\).*/\\1/p')
SLOT_AT=$(echo "$LINE" | $BB sed -n 's/.*SLOT_AT=\\([0-9a-fA-F]*\\).*/\\1/p')
[ -n "$STUB_AT" ] && [ -n "$SLOT_AT" ]

# 1. Volatile RAM patch on CameraOnDemandSaver.so (zero /usr flash write)
"$D/checked_mempatch.elf" "$P" "$STUB_AT" "$D/blobs/stub-before.bin" "$D/blobs/stub-after.bin" arm-volatile
if ! "$D/checked_mempatch.elf" "$P" "$SLOT_AT" "$D/blobs/slot-before.bin" "$D/blobs/slot-after.bin" arm-volatile; then
  "$D/checked_mempatch.elf" "$P" "$STUB_AT" "$D/blobs/stub-after.bin" "$D/blobs/stub-before.bin" arm-volatile || true
  exit 1
fi

# 2. Check and enable RTOS MemAreaMSDebug_RAW gate (tag=1, no decomp)
"$D/rtos_raw_gate.elf" status
"$D/rtos_raw_gate.elf" enable
echo "RAW_CAPTURE_ARMED: Press shutter once, then check /log/raw_capture_v01/complete.bin"
"""
    (OUT / "arm-raw-capture.sh").write_text(arm_script, encoding="ascii", newline="\n")

    install_uvc = f"""#!/bin/sh
set -eu
BB=/bin/busybox
D=/log/raw_uvc_v01
B=/usr/share/raw-uvc-v01-backup
hash() {{ $BB md5sum "$1" | $BB cut -d ' ' -f 1; }}
guard() {{ [ "$(hash "$1")" = "$2" ] || {{ echo "HASH_FAILED:$1"; exit 1; }}; }}

P=$($BB pidof im.elf)
case "$P" in ''|*[!0-9]*) echo "INVALID_PID:$P"; exit 1;; esac
if $BB grep -E 'libInfraStreamingUsb|yuy2_|raw_uvc_' /proc/$P/maps; then echo COLD_BOOT_REQUIRED; exit 1; fi
guard /setting/DmmConfig.bin 9f197ff9b300e49ab531b6f9e794253e
guard "$D/raw_uvc_v01.so" "{hashes['raw_uvc_v01.so']}"
guard "$D/libInfraStreamingUsb.so" "{hashes['libInfraStreamingUsb.so']}"
guard "$D/usbg_video.ko" "{hashes['usbg_video.ko']}"

DONE=0
finish() {{
    RC=$?
    trap - 0
    set +e
    $BB sync
    $BB mount -o remount,ro /usr || RC=1
    [ "$DONE" = 1 ] || echo RAW_UVC_INSTALL_INCOMPLETE
    exit "$RC"
}}
$BB mount -o remount,rw /usr
trap finish 0
trap 'exit 1' 1 2 15

if [ ! -d "$B" ]; then
    $BB mkdir -p "$B"
    $BB cp /usr/lib/libInfraStreamingUsb.so "$B/libInfraStreamingUsb.before.so"
    $BB cp /usr/kmod/usbg_video.ko "$B/usbg_video.before.ko"
fi

$BB cp "$D/raw_uvc_v01.so" /usr/lib/.raw_uvc_v01.new
$BB cp "$D/libInfraStreamingUsb.so" /usr/lib/.libInfraStreamingUsb.raw.new
$BB cp "$D/usbg_video.ko" /usr/kmod/.usbg_video.raw.new
$BB chmod 755 /usr/lib/.raw_uvc_v01.new /usr/lib/.libInfraStreamingUsb.raw.new
$BB chmod 644 /usr/kmod/.usbg_video.raw.new
guard /usr/lib/.raw_uvc_v01.new "{hashes['raw_uvc_v01.so']}"
guard /usr/lib/.libInfraStreamingUsb.raw.new "{hashes['libInfraStreamingUsb.so']}"
guard /usr/kmod/.usbg_video.raw.new "{hashes['usbg_video.ko']}"
$BB mv /usr/lib/.raw_uvc_v01.new /usr/lib/raw_uvc_v01.so
$BB mv /usr/lib/.libInfraStreamingUsb.raw.new /usr/lib/libInfraStreamingUsb.so
$BB mv /usr/kmod/.usbg_video.raw.new /usr/kmod/usbg_video.ko
$BB sync
DONE=1
echo "RAW_UVC_V01_INSTALLED: Select USB Streaming on camera to stream 6144x4100 ZVRAW001"
"""
    (OUT / "install-uvc.sh").write_text(install_uvc, encoding="ascii", newline="\n")

    rollback_uvc = """#!/bin/sh
set -eu
BB=/bin/busybox
B=/usr/share/raw-uvc-v01-backup
[ -f "$B/libInfraStreamingUsb.before.so" ]
[ -f "$B/usbg_video.before.ko" ]
$BB mount -o remount,rw /usr
trap '$BB sync; $BB mount -o remount,ro /usr' 0
$BB cp "$B/libInfraStreamingUsb.before.so" /usr/lib/libInfraStreamingUsb.so
$BB cp "$B/usbg_video.before.ko" /usr/kmod/usbg_video.ko
$BB chmod 755 /usr/lib/libInfraStreamingUsb.so
$BB chmod 644 /usr/kmod/usbg_video.ko
$BB rm -f /usr/lib/raw_uvc_v01.so
echo "RAW_UVC_V01_ROLLED_BACK"
"""
    (OUT / "rollback-uvc.sh").write_text(rollback_uvc, encoding="ascii", newline="\n")

    manifest = {
        "name": "raw_uvc_v01",
        "route": "Route 1: MemAreaMSDebug_RAW still RAW -> full-size UVC (6144x4100 YUY2 container, 82x614400B yc42_chunk)",
        "camera_tested": False,
        "uvc_width": 6144,
        "uvc_height": 4100,
        "uvc_frame_bytes": 50380800,
        "uvc_chunks_per_frame": 82,
        "chunk_bytes": 614400,
        "interval_100ns": 2000000,
        "files": {f: {"bytes": (OUT / f).stat().st_size, "md5": hashes[f]} for f in artifacts},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
