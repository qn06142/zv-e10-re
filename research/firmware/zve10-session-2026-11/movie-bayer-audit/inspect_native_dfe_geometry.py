"""Run real native mode headers and capture original geometry diagnostics.

No replacement sensor geometry is injected. MMIO is RAM; this is not a camera
capture. Variadic arguments are recorded as words, without guessing field units.
"""
import argparse,json,sys
from pathlib import Path
from unicorn import UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_PC,UC_ARM_REG_C1_C0_2,UC_ARM_REG_FPEXC
p=argparse.ArgumentParser(description=__doc__);p.add_argument('repo',type=Path);a=p.parse_args()
sys.path.insert(0,str(a.repo/'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness,MEM
from rtos import word,DATA,BASE,cstr
rows=[]
native_params={r['sensor_mode']:bytes.fromhex(r['drv_param_hex']) for r in
               json.loads((Path(__file__).parent/'movie-native-param-results.json').read_text())['rows']}
for sensor,drive in [('0x5',0x17),('0x7',0x18),('0x1f',4),('0xb5',0x94)]:
    h=Harness();h.u.mem_map(0xfc000000,0x400000)
    h.u.reg_write(UC_ARM_REG_C1_C0_2,0xf00000);h.u.reg_write(UC_ARM_REG_FPEXC,0x40000000)
    for fn in [0x63ae1ba4,0x635df208,0x635df224]:h.callbacks[fn]=lambda args:h.ret(0)
    diagnostics=[]
    def log(args):
        sp=h.u.reg_read(UC_ARM_REG_SP)
        diagnostics.append(dict(format=cstr(args[0]),register_words=args[1:],
                                stack_words=[h.word(sp+i*4) for i in range(16)]))
        h.ret(0)
    h.callbacks[0x6396f8c4]=log
    aif_writes=[]
    def record_aif_write(cpu, access, address, size, value, data):
        aif_writes.append(dict(pc=hex(cpu.reg_read(UC_ARM_REG_PC)),
                               address=hex(address), size=size, value=hex(value)))
    h.u.hook_add(UC_HOOK_MEM_WRITE,record_aif_write,begin=0xfc0ac000,end=0xfc0acfff)
    h.run(0x6379d44c);h.run(0x6379bf60);h.run(0x637a6d90)
    constructor_aif_writes=list(aif_writes)
    aif_writes.clear()
    table=word(0x64638120+0x4490)
    resources={h.word(h.word(table+i*4)+4):h.word(table+i*4) for i in range(27)}
    resource=h.run(0x637a6d78,drive,MEM)
    op=resources[resource];h.put(op,123);h.put(op+8,0xba)
    h.callbacks[0x6379be60]=lambda args:h.ret(op)
    h.run(0x63d26a42,word(0x64638120+0x49e4),72,0,0,1)
    owner=h.run(0x637a6e88,0,drive,0);runtime=h.run(0x637a6c84,drive,0)
    h.u.mem_write(owner,DATA[owner-BASE:owner-BASE+0xc0])
    zpd_descriptors=[]
    def observe_zpd_descriptor(args):
        dma, descriptor = args[:2]
        zpd_descriptors.append(dict(dma_object=hex(dma), bank=hex(h.word(dma+4)),
                                    port=h.u.mem_read(dma+8,1)[0],
                                    words=[hex(h.word(descriptor+i)) for i in range(0,0x28,4)]))
    # Observe the callsite inside ZpdPre's native header method before the BL.
    h.callbacks[0x63d271e6]=observe_zpd_descriptor
    for i,v in enumerate([drive,owner,runtime,0]):h.put(MEM+i*4,v)
    assert h.run(0x6379a510,op,123,MEM)==0
    header_logs=list(diagnostics);stages=[]
    common_records=[]
    cam_aif_parameter_calls=[]
    def observe_cam_aif_parameters(args):
        obj, params = args[:2]
        logical = h.u.mem_read(obj+8, 1)[0]
        if logical in (7, 8):
            cam_aif_parameter_calls.append(dict(logical=logical, object=hex(obj),
                                                enable_byte=h.u.mem_read(h.word(params)+0x10, 1)[0]))
    h.callbacks[0x6379e1f4]=observe_cam_aif_parameters
    def observe_common(args):
        common_records.append(bytes(h.u.mem_read(args[2],0x28)).hex())
        # Observation only; execute the real final setup after this hook.
    h.callbacks[0x6379a57c]=observe_common
    for encoding in [None,2,8]:
        diagnostics.clear()
        if encoding is not None:
            aif_writes.clear()
            cam_aif_parameter_calls.clear()
        if encoding is not None:
            h.u.mem_write(MEM+0x1000,native_params[sensor])
            h.u.mem_write(MEM+0x2000,bytes(0x34))
            h.put(MEM+0x2004,drive);h.put(MEM+0x2010,encoding)
            status=h.run(0x6379cb68,123,MEM+0x1000,MEM+0x2000,0,0)
            assert status == 0, (sensor, encoding, status)
            assert [call['logical'] for call in cam_aif_parameter_calls] == [7, 8]
        assert not aif_writes, (sensor, encoding, aif_writes)
        parameter_logs=list(diagnostics);dumps=[]
        for label,obj in [('ifmt',0x6426aeb8),('receiver',0x6426acdc),
                          ('link',0x6426b0b8),('img',0x6426af28),('ofmt',0x6426afdc),('mwrap',0x6426acc0)]:
            diagnostics.clear()
            fn=h.word(h.word(obj)+0x1c)&~1
            h.run(fn,obj)
            typename=cstr(h.word(h.word(h.word(obj)-4)+4))
            dumps.append(dict(label=label,object=hex(obj),rtti=typename,native_dump=hex(fn),diagnostics=list(diagnostics)))
        stages.append(dict(stage='header_only' if encoding is None else 'full_native_parameters',
                           encoder_input=encoding,common_record=None if encoding is None else common_records[-1],
                           parameter_diagnostics=parameter_logs, aif_7_8_bank_writes=list(aif_writes),
                           cam_aif_parameter_calls=list(cam_aif_parameter_calls), dumps=dumps))
    rows.append(dict(sensor=sensor,drive=hex(drive),resource=hex(resource),owner=hex(owner),
                     constructor_aif_7_8_bank_writes=constructor_aif_writes,header_diagnostics=header_logs,
                     zpd_pre_header_descriptors=zpd_descriptors,stages=stages))
print(json.dumps(dict(cases=len(rows),native_header_apply='0x6379a510',
    mocks=['atexit','OS locks','logger','operation lookup returns native default resource','harness memory helpers'],mmio_is_ram=True,
    explicit_fixtures=['clock input72','native driver-query bytes from prior verifier','encoder inputs2/8'],
    full_native_parameter_builder='0x6379cb68',full_native_final_setup='0x6379a57c',
    sensor_geometry_substituted=False,pixels_emulated=False,rows=rows),indent=2))
