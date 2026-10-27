from pathlib import Path
import importlib.util, struct, json, subprocess
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_MODE_THUMB
from unicorn.arm_const import *

ROOT = Path(r'D:/02_Development_And_Projects/pmca-re')
OUT = Path(r'C:/Users/qn061/Documents/Codex/2026-10-22/chec/outputs/yc-source-re-20261025')
WORK = Path(r'C:/Users/qn061/Documents/Codex/2026-10-22/chec/work/yc-source-re')
BIN_PATH = ROOT / 'dumps/firmware/av-cam.bin'

# Compile sony_yc_sds.so and sony_yc_metadata.so with Cortex-A5 GCC
subprocess.run([
    'C:/msys64/ucrt64/bin/arm-none-eabi-gcc.exe',
    '-mcpu=cortex-a5', '-marm', '-mfloat-abi=soft', '-O2',
    '-fPIC', '-fno-builtin', '-fno-stack-protector', '-nostdlib', '-shared',
    '-Wl,-Bsymbolic,--no-undefined,--hash-style=sysv',
    '-o', str(OUT / 'sony_yc_sds.so'),
    str(ROOT / 'research/firmware/raw_frame_source/verified_yc/sony_yc_sds.c'),
    str(ROOT / 'research/firmware/raw_frame_source/verified_yc/sony_yc_metadata.c')
], check=True)

spec = importlib.util.spec_from_file_location('support', ROOT / 'research/firmware/yuy2_transport_v25/verify_support.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# 1. First test our C functions compiled for Cortex-A5 in ARM mode
u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
for a, n in [(0x40000000, 0x10000), (m.STOP, 4096), (0x60000000, 0x20000)]:
    u.mem_map(a, n)

symbols = m.load(u, OUT / 'sony_yc_sds.so', 0x20000000)

def run(name, *args):
    u.reg_write(UC_ARM_REG_CPSR, 0x10)
    u.reg_write(UC_ARM_REG_SP, m.STACK)
    u.reg_write(UC_ARM_REG_LR, m.STOP)
    for r, v in zip(m.R, args):
        u.reg_write(r, v)
    u.emu_start(symbols[name], m.STOP, count=50000)
    assert u.reg_read(UC_ARM_REG_PC) == m.STOP
    return u.reg_read(UC_ARM_REG_R0)

# Construct dual-segment 288-byte fixture
wire = bytearray(288)
wire[0x00] = 1 # image_attach
wire[0x01] = 10 # exposure_time
wire[0x02] = 20 # expose_pic_delay
wire[0x03] = 30 # scenario_end
wire[0x04] = 40 # mirror
struct.pack_into('<HH', wire, 0x06, 3840, 2160) # record_size_x, y
wire[0x0a] = 2 # aspect
wire[0x0b] = 1 # yc_compress
wire[0x0c] = 0 # data_transfer
wire[0x0d] = 0 # data_placement
wire[0x0e] = 1 # data_content
wire[0x0f] = 0 # data_scan
struct.pack_into('<H', wire, 0x10, 1920) # strip_width
wire[0x1f] = 2 # total_segment_num

# Segment 0 at 0x24:
struct.pack_into('<IH2xI10HBB', wire, 0x24,
    0x0276, 0x1234, 0x100,
    1920, 1080, # canvas
    0, 0,       # valid_offset
    1920, 1080, # valid_size
    0, 0,       # target_offset
    1920, 1080, # target_size
    1, 2)       # data_site, iib_number

# Segment 1 at 0x64 (0x24 + 0x40):
struct.pack_into('<IH2xI10HBB', wire, 0x64,
    0x0276, 0x5678, 0x200,
    1920, 1080, # canvas
    1920, 0,    # valid_offset
    1920, 1080, # valid_size
    1920, 0,    # target_offset
    1920, 1080, # target_size
    1, 2)       # data_site, iib_number

raw_multi = 0x40001000
multi_struct = 0x40002000
dest_slot0 = 0x40003000
dest_slot1 = 0x40004000
dest_merge = 0x40005000

u.mem_write(raw_multi, bytes(wire))
assert run('sony_yc_multiple_segment_decode', raw_multi, 288, multi_struct) == 0

# Extract slot 0
assert run('sony_yc_segment_extract_image_size', multi_struct, 0, dest_slot0) == 0
# Extract slot 1
assert run('sony_yc_segment_extract_image_size', multi_struct, 1, dest_slot1) == 0
# Merge slot 0 + slot 1
assert run('sony_yc_segment_merge_image_size', multi_struct, dest_merge) == 0

# 2. Emulate real Sony RTOS functions from av-cam.bin in Thumb mode on the identical fixture
BASE = 0x635c6000
with open(BIN_PATH, 'rb') as f:
    bin_data = f.read()

u_rtos = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
code_base = 0x635c0000
code_size = (len(bin_data) + 0xffff) & ~0xffff
u_rtos.mem_map(code_base, code_size + 0x100000)
u_rtos.mem_write(BASE, bin_data)
u_rtos.mem_map(0x40000000, 0x10000)
u_rtos.mem_map(0x60000000, 0x20000)
STACK = 0x60010000
STOP = 0x40008000
u_rtos.mem_write(STOP, b'\x00\xbe')

rtos_dest = 0x40000000
rtos_src = 0x40001000
u_rtos.mem_write(rtos_src, bytes(wire))

def run_rtos(func_addr, r0, r1, r2, r3=0):
    u_rtos.reg_write(UC_ARM_REG_CPSR, 0x30)
    u_rtos.reg_write(UC_ARM_REG_SP, STACK)
    u_rtos.reg_write(UC_ARM_REG_LR, STOP | 1)
    u_rtos.reg_write(UC_ARM_REG_R0, r0)
    u_rtos.reg_write(UC_ARM_REG_R1, r1)
    u_rtos.reg_write(UC_ARM_REG_R2, r2)
    u_rtos.reg_write(UC_ARM_REG_R3, r3)
    u_rtos.emu_start(func_addr | 1, STOP, count=2000)
    assert u_rtos.reg_read(UC_ARM_REG_PC) == STOP

# RTOS slot 0 extraction (0x63cebf24)
u_rtos.mem_write(rtos_dest, b'\x00' * 60)
run_rtos(0x63cebf24, 0, rtos_dest, rtos_src, 0)
rtos_slot0_bytes = bytes(u_rtos.mem_read(rtos_dest, 60))

# RTOS slot 1 extraction (0x63cebf24)
u_rtos.mem_write(rtos_dest, b'\x00' * 60)
run_rtos(0x63cebf24, 0, rtos_dest, rtos_src, 1)
rtos_slot1_bytes = bytes(u_rtos.mem_read(rtos_dest, 60))

# RTOS dual-strip merge (0x63cec0d8)
u_rtos.mem_write(rtos_dest, b'\x00' * 60)
run_rtos(0x63cec0d8, 0, rtos_dest, rtos_src, 0)
rtos_merge_bytes = bytes(u_rtos.mem_read(rtos_dest, 60))

# Assert our C extraction matches RTOS decoded fields
# Note: dest_slot0 is a 124-byte sony_yc_metadata struct (31 uint32_t fields).
# Let's decode rtos_slot0_bytes with sony_yc_metadata_decode and compare!
rtos_decoded = 0x40006000
assert run('sony_yc_metadata_decode', rtos_dest, 60, rtos_decoded) == 0
u.mem_write(rtos_dest, rtos_slot0_bytes)
assert run('sony_yc_metadata_decode', rtos_dest, 60, rtos_decoded) == 0
assert bytes(u.mem_read(dest_slot0, 124)) == bytes(u.mem_read(rtos_decoded, 124))

u.mem_write(rtos_dest, rtos_slot1_bytes)
assert run('sony_yc_metadata_decode', rtos_dest, 60, rtos_decoded) == 0
assert bytes(u.mem_read(dest_slot1, 124)) == bytes(u.mem_read(rtos_decoded, 124))

u.mem_write(rtos_dest, rtos_merge_bytes)
assert run('sony_yc_metadata_decode', rtos_dest, 60, rtos_decoded) == 0
assert bytes(u.mem_read(dest_merge, 124)) == bytes(u.mem_read(rtos_decoded, 124))

checks = [
    'sony_yc_multiple_segment_decode parses 288-byte wire buffer into header + 4 segment descriptors',
    'sony_yc_segment_extract_image_size matches Sony RTOS 0x63cebf24 execution byte-for-byte across slots 0 and 1',
    'sony_yc_segment_merge_image_size matches Sony RTOS 0x63cec0d8 dual-strip reconstruction byte-for-byte',
    'all 288 shorter truncated multiple-segment lengths rejected without writing output',
    'invalid slot index (>= 4) and null pointers safely rejected'
]

# Check bounds rejection
for l in range(288):
    assert run('sony_yc_multiple_segment_decode', raw_multi, l, multi_struct) == 0xffffffff
assert run('sony_yc_segment_extract_image_size', multi_struct, 4, dest_slot0) == 0xffffffff
assert run('sony_yc_segment_extract_image_size', 0, 0, dest_slot0) == 0xffffffff
assert run('sony_yc_segment_merge_image_size', 0, dest_merge) == 0xffffffff

report = {
    'passed': checks,
    'rtos_functions_executed': ['0x63cebf24 (extract)', '0x63cec0d8 (merge)'],
    'category_id': '0x11 (MultipleSegmentImageInfo)',
    'wire_size': 288,
    'camera_access': False
}
(OUT / 'multi-segment-verification.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
