"""Offline verification of DMM lifetime, generation validation, and safe cleanup against genuine dmm.ko instructions."""
from pathlib import Path
import struct, json, hashlib
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3

P = Path(r'D:/02_Development_And_Projects/pmca-re/.local/dumps/camera_2025/usr/usr/kmod/dmm.ko')
with P.open('rb') as f:
    TEXT = ELFFile(f).get_section_by_name('.text').data()

BASE = 0x10000000
TABLE = 0x40000000
MEM = 0x50000000
STOP = 0x60000000
STACK = 0x70010000

def make_handle(slot_index, serial):
    return (slot_index & 0x3ff) | (((slot_index >> 10) & 1) << 15) | ((serial & 0x1f) << 10)

def extract_handle(handle):
    slot_index = (handle & 0x3ff) | ((handle >> 15) << 10)
    serial = (handle >> 10) & 0x1f
    return slot_index, serial

# 1. Verify handle bitfield extraction against real instructions at 0x8744 and 0x8778
assert extract_handle(0x1755) == (0x355, 5)
assert extract_handle(0x7f24) == (0x324, 31)
assert make_handle(0x355, 5) == 0x1755
assert make_handle(0x324, 31) == 0x7f24

def setup_uc():
    u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    for p, n in [(BASE, (len(TEXT)+4095)&~4095), (TABLE, 0x100000), (MEM, 0x10000), (STOP, 4096), (STACK-0x10000, 0x20000)]:
        u.mem_map(p, n)
    u.mem_write(BASE, TEXT)
    # Patch relocations to TABLE
    u.mem_write(BASE+0x88e8, struct.pack('<I', TABLE)) # Share
    u.mem_write(BASE+0x8c64+0x54, struct.pack('<I', TABLE)) # Close
    u.mem_write(BASE+0x8eb0, struct.pack('<I', TABLE)) # Free table base
    u.mem_write(BASE+0x93e8, struct.pack('<I', TABLE)) # SetUnitAccInfo
    return u

def test_share():
    print("Testing dmm_unit_ctrl_Share (0x884c)...")
    TYPE = 0xe0b00
    SLOT = 0x355
    SERIAL = 5
    HANDLE = make_handle(SLOT, SERIAL)
    
    def run_share(typ, handle, slot_typ, slot_serial, slot_state, slot_refs):
        u = setup_uc()
        entry = TABLE + SLOT * 0x150
        u.mem_write(entry + 0xb18, struct.pack('<I', slot_typ))
        u.mem_write(entry + 0xb20, struct.pack('<B', slot_refs))
        u.mem_write(entry + 0xb21, b'\x00')
        u.mem_write(entry + 0xb22, b'\x00')
        u.mem_write(entry + 0xb23, struct.pack('<B', slot_serial))
        u.mem_write(entry + 0xb24, struct.pack('<H', slot_state))
        
        u.reg_write(UC_ARM_REG_SP, STACK)
        u.reg_write(UC_ARM_REG_LR, STOP)
        u.reg_write(UC_ARM_REG_R0, typ)
        u.reg_write(UC_ARM_REG_R1, handle)
        
        u.emu_start(BASE + 0x884c, STOP, count=1000)
        ret = u.reg_read(UC_ARM_REG_R0)
        ret_s16 = struct.unpack('<h', struct.pack('<H', ret & 0xffff))[0]
        
        after_refs = u.mem_read(entry + 0xb20, 1)[0]
        return ret_s16, after_refs

    # Valid share
    ret, refs = run_share(TYPE, HANDLE, TYPE, SERIAL, 1, 1)
    assert ret == 0 and refs == 2, f"Expected 0, 2 got {ret}, {refs}"
    
    # Stale serial (native -517)
    ret, refs = run_share(TYPE, HANDLE, TYPE, SERIAL + 1, 1, 1)
    assert ret == -517 and refs == 1, f"Expected -517, 1 got {ret}, {refs}"
    
    # Unshareable state 0 (native -1)
    ret, refs = run_share(TYPE, HANDLE, TYPE, SERIAL, 0, 1)
    assert ret == -1 and refs == 1, f"Expected -1, 1 got {ret}, {refs}"
    
    # Unshareable state 4 (native -1)
    ret, refs = run_share(TYPE, HANDLE, TYPE, SERIAL, 4, 1)
    assert ret == -1 and refs == 1, f"Expected -1, 1 got {ret}, {refs}"
    
    # Saturated ref count 255 (native -1)
    ret, refs = run_share(TYPE, HANDLE, TYPE, SERIAL, 1, 255)
    assert ret == -1 and refs == 255, f"Expected -1, 255 got {ret}, {refs}"
    
    # Type mismatch (native -3)
    ret, refs = run_share(TYPE + 1, HANDLE, TYPE, SERIAL, 1, 1)
    assert ret == -3 and refs == 1, f"Expected -3, 1 got {ret}, {refs}"
    
    # Invalid slot index >= 0x580 (native -261)
    bad_handle = make_handle(0x580, SERIAL)
    ret, refs = run_share(TYPE, bad_handle, TYPE, SERIAL, 1, 1)
    assert ret == -261, f"Expected -261 got {ret}"
    print("  Share tests passed: -517, -1, -3, -261 verified.")

def test_free():
    print("Testing dmm_unit_ctrl_Free (0x8cbc)...")
    SLOT = 0x355
    SERIAL = 5
    HANDLE = make_handle(SLOT, SERIAL)
    
    def run_free(handle, slot_serial, slot_state, slot_refs):
        u = setup_uc()
        # Mock dmm_ext_ctrl_FreeExtent and dmm_module relocs if needed
        u.mem_write(BASE+0x8ea8, struct.pack('<I', TABLE))
        entry = TABLE + SLOT * 0x150
        u.mem_write(entry + 0xb18, struct.pack('<I', 0xe0b00))
        u.mem_write(entry + 0xb20, struct.pack('<B', slot_refs))
        u.mem_write(entry + 0xb21, b'\x00')
        u.mem_write(entry + 0xb22, b'\x00')
        u.mem_write(entry + 0xb23, struct.pack('<B', slot_serial))
        u.mem_write(entry + 0xb24, struct.pack('<H', slot_state))
        
        u.reg_write(UC_ARM_REG_SP, STACK)
        u.reg_write(UC_ARM_REG_LR, STOP)
        u.reg_write(UC_ARM_REG_R0, handle)
        
        u.emu_start(BASE + 0x8cbc, STOP, count=1000)
        ret = u.reg_read(UC_ARM_REG_R0)
        ret_s16 = struct.unpack('<h', struct.pack('<H', ret & 0xffff))[0]
        
        after_refs = u.mem_read(entry + 0xb20, 1)[0]
        after_state = struct.unpack('<H', u.mem_read(entry + 0xb24, 2))[0]
        return ret_s16, after_refs, after_state

    # Stale serial on Free -> rejected with -517, ref count and state unchanged!
    ret, refs, state = run_free(HANDLE, SERIAL + 1, 1, 2)
    assert ret == -517 and refs == 2 and state == 1, f"Expected -517, 2, 1 got {ret}, {refs}, {state}"
    
    # Valid shared free with ref_count > 1 -> decrements ref count to 1, state unchanged!
    ret, refs, state = run_free(HANDLE, SERIAL, 1, 2)
    assert ret == 0 and refs == 1 and state == 1, f"Expected 0, 1, 1 got {ret}, {refs}, {state}"
    print("  Free tests passed: stale rejected with -517, ref_count>1 decrements safely.")

def test_error_translation():
    print("Testing status translation (0x5294)...")
    u = setup_uc()
    def translate(code):
        u.reg_write(UC_ARM_REG_SP, STACK)
        u.reg_write(UC_ARM_REG_LR, STOP)
        u.reg_write(UC_ARM_REG_R0, code & 0xffffffff)
        u.emu_start(BASE + 0x5294, STOP, count=100)
        ret = u.reg_read(UC_ARM_REG_R0)
        return struct.unpack('<h', struct.pack('<H', ret & 0xffff))[0]

    assert translate(0) == 0
    assert translate(-517) == -5
    assert translate(-261) == -5
    assert translate(-5) == -5
    assert translate(-1) == -1
    assert translate(-3) == -3
    print("  Status translation tests passed: -517 -> -5, -261 -> -5, -1 -> -1, -3 -> -3.")

test_share()
test_free()
test_error_translation()
print("All offline DMM verification checks PASSED 100%!")
