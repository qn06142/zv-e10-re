"""Run native movie Mwrap header scripts and transfer-counter getters.

Counter registers are marked fixtures, not recovered frame pointers. Native
diagnostic argument order at 0x637a2448 identifies +44/+54 as tcnt.
"""
import argparse,json,sys
from pathlib import Path
from unicorn import UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_SP
p=argparse.ArgumentParser(description=__doc__);p.add_argument('repo',type=Path);a=p.parse_args()
sys.path.insert(0,str(a.repo/'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness,MEM
from rtos import cstr
h=Harness();h.u.mem_map(0xfc000000,0x100000)
logs=[]
h.callbacks[0x6396f8c4]=lambda args:(logs.append(args),h.ret(0))
# Original Mwrap constructor: output0, variant0 -> physical basefc0a7000.
h.run(0x637a2608,MEM,0,0)
assert h.word(MEM+4)==0xfc0a7000
writes=[]
h.u.hook_add(UC_HOOK_MEM_WRITE,lambda u,access,addr,size,value,data:writes.append((addr,size,value)),begin=0xfc000000,end=0xfc0fffff)
rows=[]
for sensor,drive,extent,pitch,packet,width,mode6c,mode70 in [
    ('0x1f',4,0x27f060,0x2f8,0x31,0x17c0,1,0),
    ('0xb5',0x94,0x20cba0,0x2f8,0x31,0x17c0,1,0),
    ('0x5',0x17,0x909c8,0x1fc,0x2c,0x7f0,0,1),
    ('0x7',0x18,0x909c8,0x1fc,0x2c,0x7f0,0,1),
    ('0xf',0x1c,0x11ac50,0x5f8,0x2c,0x17e0,0,1)]:
    owner=h.run(0x637a6e88,0,drive,0)
    script=h.word(owner+0x38)
    expected=[]
    for i in range(1024):
        address=h.word(script+8*i)
        if not address:break
        expected.append((address,4,h.word(script+8*i+4)))
    else:raise AssertionError('script not terminated')
    for sentinel in [0x01234560,0xff654320]:
        h.u.mem_write(0xfc0a7000,bytes(0x1000));writes.clear();logs.clear()
        h.put(0xfc0a7044,sentinel);h.put(0xfc0a7054,sentinel^0x1000)
        h.put(MEM+0x104,owner)
        h.run(0x63d24fc8,MEM,MEM+0x100)
        assert writes==expected and len(writes)==25 and not logs
        assert h.word(0xfc0a7018)==extent
        assert h.word(0xfc0a701c)==pitch
        assert h.word(0xfc0a7064)==packet and h.word(0xfc0a7068)==width
        assert h.word(0xfc0a706c)==mode6c and h.word(0xfc0a7070)==mode70
        assert h.word(0xfc0a7044)==sentinel
        assert h.word(0xfc0a7054)==sentinel^0x1000
        report0=h.run(0x63d25034,0xfc0a7000)
        report1=h.run(0x63d2504c,0xfc0a7000)
        assert report0==sentinel&0x01ffffff
        assert report1==(sentinel^0x1000)&0x01ffffff
        rows.append(dict(sensor=sensor,drive=hex(drive),owner=hex(owner),script=hex(script),
            writes=[dict(address=hex(addr),value=hex(v)) for addr,size,v in writes],
            fixture_counter_register=hex(sentinel),reported_fixture_counters=[hex(report0),hex(report1)]))
diagnostic_calls=[]
def diagnostic(args):
    sp=h.u.reg_read(UC_ARM_REG_SP)
    diagnostic_calls.append(dict(format=cstr(args[0]),register_args=args[1:],
                                stack_args=[h.word(sp+i*4) for i in range(6)]))
    h.ret(0)
h.callbacks[0x6396f8c4]=diagnostic
for offset,value in [(0x14,3),(0x40,2),(0x50,4),(0x44,0xff123450),
                     (0x54,0xfe654320),(0x4c,1),(0x5c,0)]:h.put(0xfc0a7000+offset,value)
h.run(0x637a2448,MEM)
assert len(diagnostic_calls)==1
assert diagnostic_calls[0]['format']=='IMG:Mwrap%d-%d trnsmode%d state%d %d tcnt%x %x status%d %d'
assert diagnostic_calls[0]['register_args']==[0,0,3]
assert diagnostic_calls[0]['stack_args']==[2,4,0x1123450,0x654320,1,0]
print(json.dumps(dict(cases=len(rows),native_constructor='0x637a2608',
    native_header_apply='0x63d24fc8',native_script_executor='0x637a6c24',
    native_report_getters=['0x63d25034','0x63d2504c'],
    counter_identification='native diagnostic argument order at 0x637a2448',
    native_diagnostic_cases=diagnostic_calls,
    native_diagnostic=cstr(0x637a24c8+0x007c4a55),
    function_mocks=['logger only'],fixtures=['RAM-backed MMIO','transfer-counter register sentinel values'],
    actual_frame_addresses_recovered=False,compressed_pixel_decode_proved=False,
    pixels_emulated=False,rows=rows),indent=2))
