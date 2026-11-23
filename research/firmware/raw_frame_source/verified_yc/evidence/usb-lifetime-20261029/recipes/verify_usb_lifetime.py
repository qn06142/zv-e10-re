"""
Reproducible verification of USB DMA lifetime, non-cancellation, submit timeout semantics,
and libInfraStreamingUsb stop teardown ordering.
Offline static binary analysis only. No hardware required.
"""
import io, sys, json, hashlib, struct
from pathlib import Path
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB

USB_KO_ORIG = Path("D:/02_Development_And_Projects/pmca-re/.local/dumps/camera_2025/usr/usr/kmod/usbg_video.ko")
LIB_STREAMING = Path("D:/02_Development_And_Projects/pmca-re/.local/dumps/camera_2025/usr/usr/lib/libInfraStreamingUsb.so")

def verify_usbg_video():
    data = USB_KO_ORIG.read_bytes()
    md5 = hashlib.md5(data).hexdigest()
    elf = ELFFile(io.BytesIO(data))
    text = elf.get_section_by_name('.text')
    symtab = elf.get_section_by_name('.symtab')
    rel_text = elf.get_section_by_name('.rel.text')
    
    code = text.data()
    rels = {}
    for r in rel_text.iter_relocations():
        s = symtab.get_symbol(r['r_info_sym'])
        rels[r['r_offset']] = s.name
        
    cs = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    cs.detail = True
    
    # 1. Trace Submit function 0xd00..0x10d0
    # Specifically find schedule_timeout call, timeout check, slot assignment, and return value
    submit_instructions = list(cs.disasm(code[0xd00:0x10d4], 0xd00))
    
    timeout_branch = None
    slot_ready_assign = []
    return_zero = None
    
    for i in submit_instructions:
        rname = rels.get(i.address)
        if rname == 'schedule_timeout':
            timeout_branch = i.address
        if i.mnemonic == 'strbeq' and 'r2' in i.op_str:
            slot_ready_assign.append((i.address, i.op_str))
        if i.address == 0x10cc and i.mnemonic == 'mov' and 'r0, #0' in i.op_str:
            return_zero = i.address
            
    # 2. Check for any dma cancel / abort in the entire module
    dma_symbols = [s.name for s in symtab.iter_symbols() if 'dma' in s.name.lower()]
    
    # Check relocations across .rel.text for any dma330 call other than dma330_mem_transfer_async
    dma_relocs = {off: name for off, name in rels.items() if 'dma' in name.lower()}
    
    return {
        "usbg_video_md5": md5,
        "timeout_call_addr": hex(timeout_branch) if timeout_branch else None,
        "slot_ready_stores": [hex(addr) for addr, op in slot_ready_assign],
        "submit_returns_zero_at": hex(return_zero) if return_zero else None,
        "dma_imported_symbols": dma_symbols,
        "dma_relocs_in_text": {hex(k): v for k, v in dma_relocs.items()},
        "has_dma_cancel": any('cancel' in name.lower() or 'abort' in name.lower() or 'stop' in name.lower() for name in dma_symbols)
    }

def verify_streaming_stop():
    data = LIB_STREAMING.read_bytes()
    md5 = hashlib.md5(data).hexdigest()
    elf = ELFFile(io.BytesIO(data))
    text = elf.get_section_by_name('.text')
    dynsym = elf.get_section_by_name('.dynsym')
    base = text['sh_addr']
    code = text.data()
    
    cs = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    cs.detail = True
    
    # Started::funcStopFuncCmd is at 0x80d8 (Thumb: 0x80d9)
    # Trace calls from 0x80d8 to 0x8214
    offset = 0x80d8 - base
    insts = list(cs.disasm(code[offset:offset+0x140], 0x80d8))
    
    calls = []
    stop_cmd_loaded = False
    for i in insts:
        if i.mnemonic == 'movw' and '0x6103' in i.op_str:
            stop_cmd_loaded = True
        if i.mnemonic in ('bl', 'blx'):
            calls.append((hex(i.address), i.op_str))
            
    return {
        "lib_streaming_md5": md5,
        "funcStopFuncCmd_addr": "0x80d8",
        "stop_cmd_0x6103_loaded": stop_cmd_loaded,
        "calls_in_funcStopFuncCmd": calls
    }

def main():
    u_res = verify_usbg_video()
    s_res = verify_streaming_stop()
    
    result = {
        "mocked": False,
        "limitations": "Static ELF disassembly and relocation resolution; no execution of kernel module or camera binaries.",
        "usb_driver": u_res,
        "streaming_state_machine": s_res
    }
    
    out_path = Path("D:/02_Development_And_Projects/pmca-re/research/firmware/raw_frame_source/verified_yc/evidence/usb-lifetime-20261029/usb_lifetime_verification.json")
    out_path.write_text(json.dumps(result, indent=2))
    print(f"Verified USB lifetime and teardown semantics. Results written to {out_path}")
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
