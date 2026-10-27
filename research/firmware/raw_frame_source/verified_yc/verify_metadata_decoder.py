import importlib.util, json, struct, subprocess
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn.arm_const import *

ROOT = Path(r'D:/02_Development_And_Projects/pmca-re')
OUT = Path(r'C:/Users/qn061/Documents/Codex/2026-10-22/chec/outputs/yc-source-re-20261025')
WORK = Path(r'C:/Users/qn061/Documents/Codex/2026-10-22/chec/work/yc-source-re')

# Recompile sony_yc_metadata.so with Cortex-A5 GCC
subprocess.run([
    'C:/msys64/ucrt64/bin/arm-none-eabi-gcc.exe',
    '-mcpu=cortex-a5', '-marm', '-mfloat-abi=soft', '-O2',
    '-fPIC', '-fno-builtin', '-fno-stack-protector', '-nostdlib', '-shared',
    '-Wl,--no-undefined,--hash-style=sysv',
    '-o', str(OUT / 'sony_yc_metadata.so'),
    str(ROOT / 'research/firmware/raw_frame_source/verified_yc/sony_yc_metadata.c')
], check=True)

spec = importlib.util.spec_from_file_location('support', ROOT / 'research/firmware/yuy2_transport_v25/verify_support.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
for a, n in [(0x40000000, 0x10000), (m.STOP, 4096), (0x60000000, 0x20000)]:
    u.mem_map(a, n)

symbols = m.load(u, OUT / 'sony_yc_metadata.so', 0x20000000)

def run(name, *args):
    u.reg_write(UC_ARM_REG_CPSR, 0x10)
    u.reg_write(UC_ARM_REG_SP, m.STACK)
    u.reg_write(UC_ARM_REG_LR, m.STOP)
    for r, v in zip(m.R, args):
        u.reg_write(r, v)
    u.emu_start(symbols[name], m.STOP, count=10000)
    assert u.reg_read(UC_ARM_REG_PC) == m.STOP
    return u.reg_read(UC_ARM_REG_R0)

raw = 0x40000001
dest = 0x40001000
span = 0x40002000
u.mem_write(raw, bytes(range(60)))
assert run('sony_yc_metadata_decode', raw, 60, dest) == 0

# Match against all 31 individual Sony SDK getters
getters_data = json.loads((OUT / 'image-size-individual-getters.json').read_text())['fields']
getters_by_offset = {x['offset']: x['value'] for x in getters_data}
field_layout = json.loads((ROOT / 'research/firmware/raw_frame_source/verified_yc/field-layout.json').read_text())
assert len(field_layout) == 31
expected_31 = [getters_by_offset[offset] for name, offset, width in field_layout]

decoded_31 = list(struct.unpack('<31I', u.mem_read(dest, 124)))
assert decoded_31 == expected_31

checks = ['all 31 normalized fields match actual Sony getter execution with unaligned input']

for length in range(60):
    u.mem_write(dest, b'\xa5' * 124)
    assert run('sony_yc_metadata_decode', raw, length, dest) == 0xffffffff
    assert bytes(u.mem_read(dest, 124)) == b'\xa5' * 124
checks.append('all 60 truncated lengths rejected without writing output')

assert run('sony_yc_metadata_decode', 0, 60, dest) == 0xffffffff
assert run('sony_yc_metadata_decode', raw, 60, 0) == 0xffffffff
checks.append('null pointer checks verified')

# Unit data offset is field 3 (normalized layout) from Sony's labeled getter (offset 12)
u.mem_write(dest + 12, struct.pack('<I', 0x100))
assert run('sony_yc_resolve_data_span', dest, 0x15000000, 0x1000, span) == 0
assert bytes(u.mem_read(span, 8)) == struct.pack('<II', 0x15000100, 0xf00)
checks.append('one DMM extent plus verified unitDataOffset resolves remaining span')

for physical, length, offset in [
    (0, 0x1000, 0),
    (0x15000000, 0, 0),
    (0x15000000, 0x1000, 0x1000),
    (0x15000000, 0x1000, 0x1001),
    (0xfffff000, 0x2000, 0)
]:
    u.mem_write(dest + 12, struct.pack('<I', offset))
    u.mem_write(span, b'\xa5' * 8)
    assert run('sony_yc_resolve_data_span', dest, physical, length, span) == 0xffffffff
    assert bytes(u.mem_read(span, 8)) == b'\xa5' * 8
checks.append('invalid extent, offset and physical wrap rejected without output changes')

u.mem_write(dest + 12, struct.pack('<I', 0xfff))
assert run('sony_yc_resolve_data_span', dest, 0xfffff000, 0x1000, span) == 0
assert bytes(u.mem_read(span, 8)) == struct.pack('<II', 0xffffffff, 1)
checks.append('last 32-bit physical byte supported without wrapping')

(OUT / 'metadata-decoder-verification.json').write_text(json.dumps({
    'passed': checks,
    'total_fields_verified': 31,
    'camera_access': False,
    'source_subscription_implemented': False
}, indent=2))

print(f'Metadata decoder checks passed: {len(checks)} categories (31 fields verified, plus 60 truncation cases)')
