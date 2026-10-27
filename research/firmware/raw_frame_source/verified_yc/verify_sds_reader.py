from pathlib import Path
import importlib.util, struct, json, subprocess
from unicorn import *
from unicorn.arm_const import *

ROOT = Path(r'D:/02_Development_And_Projects/pmca-re')
OUT = Path(r'C:/Users/qn061/Documents/Codex/2026-10-22/chec/outputs/yc-source-re-20261025')
spec = importlib.util.spec_from_file_location('support', ROOT / 'research/firmware/yuy2_transport_v25/verify_support.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
handlers = {}
calls = []
for a, n in [(0x10000000, 0x10000), (0x40000000, 0x10000), (m.STOP, 4096), (0x60000000, 0x20000)]:
    u.mem_map(a, n)

def imp(name):
    a = 0x10000000 + len(handlers) * 4
    handlers[a] = name
    return a

sdk = m.load(u, ROOT / 'dumps/camera_2025/usr/usr/lib/dataflowInfraFramework.so', 0x08000000, imp)

def hook(u, a, n, d):
    if a not in handlers: return
    name = handlers[a]
    r = [u.reg_read(x) for x in m.R]
    calls.append(name)
    if name in sdk:
        u.reg_write(UC_ARM_REG_PC, sdk[name])
        return
    if name == 'memset':
        u.mem_write(r[0], bytes([r[1] & 255]) * r[2])
        v = r[0]
    elif name == 'memcpy':
        u.mem_write(r[0], bytes(u.mem_read(r[1], r[2])))
        v = r[0]
    elif name in ['memcmp', 'strncmp']:
        v = int(bytes(u.mem_read(r[0], r[2])) != bytes(u.mem_read(r[1], r[2])))
    else:
        raise AssertionError((name, [hex(x) for x in r]))
    u.reg_write(UC_ARM_REG_R0, v)
    u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

u.hook_add(UC_HOOK_CODE, hook)

def run(name, *args):
    u.reg_write(UC_ARM_REG_CPSR, 0x10)
    u.reg_write(UC_ARM_REG_SP, m.STACK)
    u.reg_write(UC_ARM_REG_LR, m.STOP)
    for r, v in zip(m.R, args):
        u.reg_write(r, v)
    u.emu_start(sdk[name], m.STOP, count=50000)
    assert u.reg_read(UC_ARM_REG_PC) == m.STOP
    return u.reg_read(UC_ARM_REG_R0)

obj = 0x40000000
raw = 0x40001000
entry = 0x40002000
entry2 = 0x40003000
output = 0x40004000

run('_ZN26C_DataflowInfra_StdData_YCC1Ejjj', obj, raw, 1024, 0)
run('_ZN28C_DataflowInfra_StdData_Base12CreateHeaderEv', obj)
run('_ZN35C_DataflowInfra_Entry_ImageSizeInfoC1Ev', entry)
tagged = bytes(range(60))
ptr = struct.unpack('<I', u.mem_read(entry + 12, 4))[0]
u.mem_write(ptr, tagged)
run('_ZN28C_DataflowInfra_StdData_Base12SetEntryDataEP26C_DataflowInfra_Entry_Base', obj, entry)
run('_ZN35C_DataflowInfra_Entry_ImageSizeInfoC1Ev', entry2)
assert run('_ZN26C_DataflowInfra_StdData_YC22GetEntry_ImageSizeInfoEP35C_DataflowInfra_Entry_ImageSizeInfo', obj, entry2) == 0
run(next(n for n in sdk if 'ImageSizeInfo11GetData_All' in n and 'Right' not in n), entry2, output)
assert bytes(u.mem_read(output, 60)) == tagged
fixture = bytes(u.mem_read(raw, 128))
(OUT / 'native-sds-fixture.bin').write_bytes(fixture)
print('Real SDK constructor, entry insertion, lookup and GetData_All passed')

WORK = Path(__file__).resolve().parent
subprocess.run([
    'C:/msys64/ucrt64/bin/arm-none-eabi-gcc.exe',
    '-mcpu=cortex-a5', '-marm', '-mfloat-abi=soft', '-O2',
    '-fPIC', '-fno-builtin', '-fno-stack-protector', '-nostdlib', '-shared',
    '-Wl,-Bsymbolic,--no-undefined,--hash-style=sysv',
    '-o', str(OUT / 'sony_yc_sds.so'),
    str(WORK / 'sony_yc_sds.c'), str(WORK / 'sony_yc_metadata.c')
], check=True)

ours = m.load(u, OUT / 'sony_yc_sds.so', 0x20000000)

def oursrun(name, *args):
    saved = sdk.get(name)
    sdk[name] = ours[name]
    try:
        return run(name, *args)
    finally:
        if saved is None: del sdk[name]
        else: sdk[name] = saved

normalized = 0x40005000
assert oursrun('sony_yc_metadata_decode', output, 60, normalized) == 0
expected = bytes(u.mem_read(normalized, 124))
u.mem_write(normalized, b'\xa5' * 124)
assert oursrun('sony_yc_sds_decode_image', raw, len(fixture), normalized) == 0
assert bytes(u.mem_read(normalized, 124)) == expected

for size in range(128):
    u.mem_write(normalized, b'\xa5' * 124)
    assert oursrun('sony_yc_sds_decode_image', raw, size, normalized) == 0xffffffff, size
    assert bytes(u.mem_read(normalized, 124)) == b'\xa5' * 124

mutations = [(0, 0), (8, 2), (12, 65), (16, 0xfffffff0), (32, 0), (44, 0xfffffff0), (48, 59), (48, 0xffffffff)]
for off, value in mutations:
    bad = bytearray(fixture)
    struct.pack_into('<I', bad, off, value)
    u.mem_write(raw, bytes(bad))
    u.mem_write(normalized, b'\xa5' * 124)
    assert oursrun('sony_yc_sds_decode_image', raw, 128, normalized) == 0xffffffff, (off, value)
    assert bytes(u.mem_read(normalized, 124)) == b'\xa5' * 124

# Missing image entry and malformed linked lists cannot escape bounded traversal.
for count, nextoff, result in [(1, 0, 0xfffffffe), (2, 32, 0xffffffff), (2, 0xfffffff0, 0xffffffff), (2, 0, 0xffffffff)]:
    bad = bytearray(fixture)
    struct.pack_into('<I', bad, 12, count)
    struct.pack_into('<I', bad, 36, 7)
    struct.pack_into('<I', bad, 52, nextoff)
    u.mem_write(raw, bytes(bad))
    assert oursrun('sony_yc_sds_decode_image', raw, 128, normalized) == result

# Genuine SDK appends a preceding unrelated entry: exercise next-entry traversal.
u.mem_write(raw, b'\0' * 1024)
run('_ZN28C_DataflowInfra_StdData_Base12CreateHeaderEv', obj)
u.mem_write(entry + 4, struct.pack('<I', 7))
assert run('_ZN28C_DataflowInfra_StdData_Base12SetEntryDataEP26C_DataflowInfra_Entry_Base', obj, entry) == 0
u.mem_write(entry + 4, struct.pack('<I', 0))
assert run('_ZN28C_DataflowInfra_StdData_Base12SetEntryDataEP26C_DataflowInfra_Entry_Base', obj, entry) == 0
assert oursrun('sony_yc_sds_decode_image', raw, 224, normalized) == 0
assert bytes(u.mem_read(normalized, 124)) == expected

# Also verify native SDK insertion and retrieval of Category 1 (YcStateInfo)
state_entry = 0x40006000
run('_ZN33C_DataflowInfra_Entry_YcStateInfoC1Ev', state_entry)
state_wire = bytes([0x10, 0x20, 0x30, 0x40, 0x50, 0x60])
state_ptr = struct.unpack('<I', u.mem_read(state_entry + 12, 4))[0]
u.mem_write(state_ptr, state_wire)
assert run('_ZN28C_DataflowInfra_StdData_Base12SetEntryDataEP26C_DataflowInfra_Entry_Base', obj, state_entry) == 0

state_out = 0x40007000
u.mem_write(state_out, b'\xa5' * 24)
assert oursrun('sony_yc_sds_decode_state', raw, 1024, state_out) == 0
state_vals = list(struct.unpack('<6I', u.mem_read(state_out, 24)))
assert state_vals == [0x10, 0x20, 0x30, 0x40, 0x50, 0x60]

report = {
    'passed': [
        'actual Sony SSYC constructor, insertion, image lookup and GetData_All executed',
        'Cortex-A5 C reader matches actual Sony returned metadata (all 31 fields verified)',
        'all 128 shorter native single-entry extents reject without changing output',
        'eight malformed headers and entry extents rejected',
        'missing entry and self/invalid/zero next links handled',
        'actual SDK-created multi-entry chain decoded (Category 0 ImageSizeInfo and Category 1 YcStateInfo verified)'
    ],
    'camera_access': False,
    'pixel_format_or_lifetime_proved': False,
    'external_functions_stubbed': ['memcpy', 'memset', 'strncmp'],
    'Sony_imports_forwarded_to_original_code': sorted({x for x in calls if x not in ['memcpy', 'memset', 'strncmp']}),
    'native_single_entry_hex': fixture.hex()
}
(OUT / 'sds-reader-verification.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report['passed'], indent=2))
