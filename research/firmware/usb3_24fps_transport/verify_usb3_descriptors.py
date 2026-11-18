#!/usr/bin/env python3
"""
Verification Script for USB 3.0 SuperSpeed UVC Descriptors & 24fps Bandwidth Feasibility.

Target Hardware: Sony ZV-E10 (CXD90045 SoC)
Analysis: Strictly Offline Static Analysis of Genuine Firmware Binaries.
"""

import json
from pathlib import Path
import struct
import sys
from elftools.elf.elffile import ELFFile

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
LIB_USB_CMN = REPO_ROOT / '.local/dumps' / "camera_2025" / "usr" / "usr" / "lib" / "libInfraUsbCmn.so"
VMLINUX = REPO_ROOT / '.local/dumps' / "firmware" / "vmlinux.bin"
AVCAM = REPO_ROOT / '.local/dumps' / "firmware" / "av-cam.bin"


def verify_kernel_dwc3(results: dict):
    """Verify DWC3 USB 3.0 SuperSpeed controller support in vmlinux.bin."""
    with open(VMLINUX, "rb") as f:
        data = f.read()

    dwc3_found = b"dwc3-gadget" in data
    set_sel_found = b"Set SEL should be 6 bytes" in data
    u1_u2_found = b"u1_u2_enable_mutex" in data
    otg_gadget_found = b"usb_otgcore: transfer to Gadget" in data

    results["kernel_dwc3_superspeed"] = {
        "dwc3_gadget_present": dwc3_found,
        "usb3_set_sel_present": set_sel_found,
        "usb3_u1_u2_power_states_present": u1_u2_found,
        "otgcore_gadget_switch_present": otg_gadget_found,
        "status": "PASS" if (dwc3_found and set_sel_found and u1_u2_found and otg_gadget_found) else "FAIL"
    }


def verify_usb_cmn_superspeed_tables(results: dict):
    """Verify native SuperSpeed descriptors in libInfraUsbCmn.so."""
    with open(LIB_USB_CMN, "rb") as f:
        elf = ELFFile(f)

        def read_vaddr(addr, length):
            for s in elf.iter_sections():
                sh_addr = s["sh_addr"]
                sh_size = s["sh_size"]
                if sh_addr <= addr < sh_addr + sh_size:
                    offset = s["sh_offset"] + (addr - sh_addr)
                    f.seek(offset)
                    return f.read(length)
            return b""

        # 1. CUsbSvc::getSpeed speed mapping table at 0x1280c
        # Indices 0..2: Full Speed (3), High Speed (1), Super Speed (2)
        speed_tbl_data = read_vaddr(0x1280c, 12)
        speed_vals = struct.unpack("<3I", speed_tbl_data)

        # 2. Check streaming_ntsc_interface_desc Set 3 (SuperSpeed) at 0x1cca0
        set3_data = read_vaddr(0x1cca0, 32)
        set3_words = struct.unpack("<8I", set3_data)
        # Entry 1 at 0x1ce1c contains pointer to endpoint descriptor
        ep_desc_ptr = set3_words[3]  # 0x1cce8

        # 3. SuperSpeed Endpoint Descriptor at 0x1cce8
        ep_data = read_vaddr(0x1cce8, 16)
        bEndpointAddress = ep_data[0]
        bmAttributes = ep_data[1]
        wMaxPacketSize = struct.unpack("<H", ep_data[2:4])[0]
        bInterval = ep_data[4]
        bMaxBurst = ep_data[5]

        # 4. Downstream VS hierarchy at 0x12625
        vs_hdr_data = read_vaddr(0x12625, 14)
        bLength, bDescType, bSubType, bNumFmt, wTotalLen = struct.unpack("<BBBBH", vs_hdr_data[:6])

        # 5. NTSC VS_FRAME descriptor at 0x1263e
        frame_data = read_vaddr(0x1263e, 30)
        f_len, f_type, f_subtype, f_idx, f_caps, wWidth, wHeight = struct.unpack("<BBB BB HH", frame_data[:9])
        dwDefInterval = struct.unpack("<I", frame_data[21:25])[0]

        speed_ok = (speed_vals == (3, 1, 2))
        ep_ok = (bEndpointAddress == 0x81 and bmAttributes == 0x02 and wMaxPacketSize == 1024)
        vs_ok = (wTotalLen == 61 and f_len == 30 and f_subtype == 0x07)

        results["libInfraUsbCmn_superspeed"] = {
            "speed_mapping_table_0x1280c": [hex(x) for x in speed_vals],
            "speed_3_maps_to_cusb_speed_super": speed_vals[2] == 2,
            "set3_superspeed_iface_desc_addr": "0x1cca0",
            "ep_descriptor_vaddr": hex(ep_desc_ptr),
            "ep_address": hex(bEndpointAddress),
            "ep_attributes": hex(bmAttributes),
            "ep_wMaxPacketSize": wMaxPacketSize,
            "ep_bMaxBurst": bMaxBurst,
            "vs_hierarchy_vaddr": "0x12625",
            "vs_wTotalLength": wTotalLen,
            "frame_wWidth": wWidth,
            "frame_wHeight": wHeight,
            "frame_default_interval_100ns": dwDefInterval,
            "status": "PASS" if (speed_ok and ep_ok and vs_ok) else "FAIL"
        }


def compute_bandwidth_budget(results: dict):
    """Compute physical transmission bandwidth requirements for >= 24fps."""
    usb3_usable_mbytes_sec = 380.0  # Real-world sustained SuperSpeed Bulk (5 Gbps 8b/10b ~ 400 MB/s theoretical)

    modes = [
        {"name": "1080p 10-bit Bayer RAW", "w": 1920, "h": 1080, "bpp": 1.25, "fps": 24},
        {"name": "1080p 10-bit Bayer RAW @ 30fps", "w": 1920, "h": 1080, "bpp": 1.25, "fps": 30},
        {"name": "1080p 12-bit Bayer RAW", "w": 1920, "h": 1080, "bpp": 1.5, "fps": 24},
        {"name": "1080p 12-bit Bayer RAW @ 30fps", "w": 1920, "h": 1080, "bpp": 1.5, "fps": 30},
        {"name": "1280p Open Gate 3:2 10-bit RAW", "w": 1920, "h": 1280, "bpp": 1.25, "fps": 24},
        {"name": "1080p YUY2 Uncompressed", "w": 1920, "h": 1080, "bpp": 2.0, "fps": 24},
        {"name": "3.2K Open Gate 3:2 10-bit RAW", "w": 3240, "h": 2160, "bpp": 1.25, "fps": 24},
    ]

    budget = []
    all_pass = True
    for m in modes:
        frame_bytes = int(m["w"] * m["h"] * m["bpp"])
        throughput_mb_s = (frame_bytes * m["fps"]) / (1024 * 1024)
        bus_util_pct = (throughput_mb_s / usb3_usable_mbytes_sec) * 100.0
        dwFrameInterval_100ns = int(round(10_000_000 / m["fps"]))
        fits = throughput_mb_s <= usb3_usable_mbytes_sec
        if not fits:
            all_pass = False

        budget.append({
            "mode": m["name"],
            "resolution": f"{m['w']}x{m['h']}",
            "fps": m["fps"],
            "frame_size_bytes": frame_bytes,
            "dwFrameInterval_100ns": dwFrameInterval_100ns,
            "throughput_MB_per_sec": round(throughput_mb_s, 2),
            "bus_utilization_pct": round(bus_util_pct, 1),
            "fits_in_usb3": fits
        })

    results["bandwidth_budget_24fps"] = {
        "usb3_usable_throughput_cap_MB_s": usb3_usable_mbytes_sec,
        "modes": budget,
        "status": "PASS" if all_pass else "FAIL"
    }


def main():
    results = {}
    print("Verifying Kernel DWC3 USB 3.0 support...")
    verify_kernel_dwc3(results)
    print("Verifying libInfraUsbCmn.so SuperSpeed tables...")
    verify_usb_cmn_superspeed_tables(results)
    print("Computing 24fps bandwidth budget...")
    compute_bandwidth_budget(results)

    out_file = Path(__file__).resolve().parent / "usb3-verification.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Verification output saved to {out_file}")
    all_pass = all(v.get("status") == "PASS" for v in results.values())
    print("OVERALL RESULT:", "PASS" if all_pass else "FAIL")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
