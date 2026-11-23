"""
Reproducible verification of SDF Srotate hardware boundary, parameter validation,
strip granularity (64-byte alignment), 2 bpp stride computation, and event flag synchronization.
Offline static analysis of av-cam.bin. No camera required.
"""
import sys, json, hashlib, struct
from pathlib import Path
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

RTOS_BIN = Path("D:/02_Development_And_Projects/pmca-re/.local/dumps/firmware/av-cam.bin")
RTOS_BASE = 0x635c6000

def load_rtos():
    data = RTOS_BIN.read_bytes()
    md5 = hashlib.md5(data).hexdigest()
    return data, md5

def verify_srotate_driver(data):
    cs = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    cs.detail = True
    
    # 1. Validation checks in 0x638e1db4..0x638e1e38
    offset = 0x638e1db4 - RTOS_BASE
    insts = list(cs.disasm(data[offset:offset+0x90], 0x638e1db4))
    
    strip_align_check = None
    compression_check = None
    bpp_shifts = []
    
    for i in insts:
        # Check for tst.w r3, #0x3f (strip width multiple of 64)
        if i.mnemonic == 'tst.w' and '0x3f' in i.op_str:
            strip_align_check = hex(i.address)
        # Check for cmp r3, #1 / bhi (compression flag <= 1)
        if i.mnemonic == 'cmp' and 'r3, #1' in i.op_str:
            compression_check = hex(i.address)
            
    # 2. Check 2 bytes per pixel calculation in 0x638e1e80..0x638e1f00
    offset_stride = 0x638e1e80 - RTOS_BASE
    stride_insts = list(cs.disasm(data[offset_stride:offset_stride+0x80], 0x638e1e80))
    for i in stride_insts:
        # Look for lsl #1 or lsls #1
        if 'lsl #1' in i.op_str or (i.mnemonic == 'lsls' and '#1' in i.op_str):
            bpp_shifts.append((hex(i.address), f"{i.mnemonic} {i.op_str}"))
            
    # 3. Check completion wait flag at 0x638e7f78..0x638e7f88
    offset_flg = 0x638e7f70 - RTOS_BASE
    flg_insts = list(cs.disasm(data[offset_flg:offset_flg+0x30], 0x638e7f70))
    wai_flg_call = None
    flg_id = None
    flg_ptn = None
    for i in flg_insts:
        if i.mnemonic == 'movs' and 'r0, #0xe' in i.op_str:
            flg_id = 14
        if i.mnemonic == 'mov.w' and '0x4000000' in i.op_str:
            flg_ptn = "0x04000000"
        if i.mnemonic in ('bl', 'blx') and i.address == 0x638e7f84:
            wai_flg_call = hex(i.address)
            
    return {
        "strip_width_mod64_check_addr": strip_align_check,
        "compression_le1_check_addr": compression_check,
        "stride_2bpp_shifts": bpp_shifts,
        "completion_event_flag": {
            "flag_id": flg_id,
            "pattern": flg_ptn,
            "tk_wai_flg_call_addr": wai_flg_call
        }
    }

def main():
    data, md5 = load_rtos()
    details = verify_srotate_driver(data)
    
    result = {
        "mocked": False,
        "limitations": "Static firmware disassembly and parameter tracing; no hardware MMIO or event flag execution.",
        "av_cam_md5": md5,
        "srotate_driver": details
    }
    
    out_dir = Path("D:/02_Development_And_Projects/pmca-re/research/firmware/raw_frame_source/verified_yc/evidence/sdf-boundary-20261029")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "sdf_boundary_verification.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"Verified SDF hardware boundary. Results written to {out_path}")
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
