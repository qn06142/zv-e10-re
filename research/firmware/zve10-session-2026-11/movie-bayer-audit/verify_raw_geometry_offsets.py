"""Native RAW geometry fields: DDR padding/offsets versus sensor crop controls.

All geometry and buffer values are fixtures. No source pixels or physical crop
behavior is modeled, and this does not validate a source rectangle.
"""
import argparse,json,struct,sys
from pathlib import Path
from unicorn import UC_HOOK_MEM_WRITE
p=argparse.ArgumentParser(description=__doc__);p.add_argument('repo',type=Path);a=p.parse_args()
sys.path.insert(0,str(a.repo/'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness,MEM
h=Harness();h.u.mem_map(0xfc000000,0x100000)
obj,dma,request,owner,geometry,param,formatter=[MEM+i*0x1000 for i in range(1,8)]
h.run(0x637a36ec,formatter,0);h.run(0x637a3be0,dma,3,0)
h.run(0x6379e248,obj,5,dma,formatter)
h.put(request+4,owner);h.put(owner+0x5c,geometry)
h.callbacks[0x6396f8c4]=lambda args:h.ret(0)
writes=[]
h.u.hook_add(UC_HOOK_MEM_WRITE,lambda u,access,addr,size,value,data:writes.append((addr,size,value)),begin=0xfc000000,end=0xfc0fffff)
rows=[];overflow_rows=[]
pitch,width,height=1984,1920,1080
for encoding,numerator,denominator in [(0,2,1),(3,3,2)]:
    baseline=None
    for left,top in [(0,0),(16,0),(0,2),(16,2)]:
        for gap_rows in [0,1]:
            h.u.mem_write(0xfc0a8000,bytes(0x2000));writes.clear()
            h.u.mem_write(geometry,struct.pack('<6H',pitch,left,top,width,height,gap_rows)+bytes(32))
            h.u.mem_write(param,bytes(0x34))
            for offset,value in [(0xc,encoding),(0x14,0x20000000),(0x18,0x1000000),(0x1c,1)]:h.put(param+offset,value)
            h.run(0x6379e2b8,obj,request,param)
            byte_pitch=pitch*numerator//denominator
            expected=[0x20000000+left*numerator//denominator+top*byte_pitch,
                      width*numerator//denominator,
                      byte_pitch-width*numerator//denominator+gap_rows*byte_pitch,
                      height-1]
            actual=[h.word(0xfc0a9220+i*4) for i in range(4)]
            assert actual==expected,(encoding,left,top,gap_rows,actual,expected)
            formatter_writes=[(hex(addr),size,hex(value)) for addr,size,value in writes if not 0xfc0a9000<=addr<0xfc0aa000]
            if baseline is None:baseline=formatter_writes
            assert formatter_writes==baseline
            assert all(0xfc0a8000<=addr<0xfc0aa000 or addr in [0xfc0a0500,0xfc0a0504,0xfc0a0560,0xfc0a0564] for addr,size,value in writes)
            rows.append(dict(encoding=encoding,pitch=pitch,left=left,top=top,
                gap_rows=gap_rows,programmed=[hex(v) for v in actual],
                formatter_and_shared_writes=formatter_writes,input_geometry_register_writes=[]))
    # Native capacity calculation omits the horizontal offset when the active
    # width plus left padding exceeds the declared pitch. A descriptor can then
    # extend beyond the accepted span even with repeat=1.
    bad_pitch,bad_left=1920,16
    capacity=bad_pitch*height*numerator//denominator
    h.u.mem_write(geometry,struct.pack('<6H',bad_pitch,bad_left,0,width,height,0)+bytes(32))
    for offset,value in [(0xc,encoding),(0x14,0x20000000),(0x18,capacity),(0x1c,1)]:h.put(param+offset,value)
    logs=[]
    h.callbacks[0x6396f8c4]=lambda args:(logs.append(args),h.ret(0))
    h.run(0x6379e2b8,obj,request,param)
    native_required=h.run(0x63d2356a,obj,owner,encoding)
    assert native_required==capacity and not logs
    base,line,gap,last=[h.word(0xfc0a9220+i*4) for i in range(4)]
    described_end=base+last*(line+gap)+line
    overflow=described_end-(0x20000000+capacity)
    assert overflow==bad_left*numerator//denominator
    overflow_rows.append(dict(encoding=encoding,pitch=bad_pitch,left=bad_left,
        active_width=width,height=height,capacity=capacity,
        native_required_size=native_required,native_logs=logs,
        programmed_base=hex(base),line_bytes=line,gap_bytes=gap,
        descriptor_end=hex(described_end),buffer_end=hex(0x20000000+capacity),
        descriptor_exceeds_capacity_by=overflow,actual_dma_executed=False))
alignment_rows=[]
for width in (15,16,17,1920,1996,2000,2004,2008,2016):
    pitch, height = 2016, 1122
    h.u.mem_write(0xfc0a8000,bytes(0x2000))
    h.u.mem_write(geometry,struct.pack('<6H',pitch,0,0,width,height,0)+bytes(32))
    h.put(param+0xc,3)
    h.put(param+0x18,0x1000000)
    logs.clear()
    h.run(0x6379e2b8,obj,request,param)
    block_word=h.word(0xfc0a8910)
    line_bytes=h.word(0xfc0a9224)
    assert line_bytes==24*((width+15)//16), (width,line_bytes)
    expected_word=(((width//16-1)<<16)+height-1)&0xffffffff
    assert block_word==expected_word and not logs, (width,hex(block_word),logs)
    alignment_rows.append(dict(active_width=width,height=height,encoding=3,
        formatter_block_word=hex(block_word),formatter_whole_blocks=width//16,
        dma_line_bytes=line_bytes,dma_blocks=line_bytes//24,native_logs=logs.copy()))
print(json.dumps(dict(cases=len(rows),native_raw_setup='0x6379e2b8',
    mocked=['logger','harness memory helpers'],
    geometry_is_fixture=True,buffer_is_fixture=True,pixels_emulated=False,
    physical_crop_behavior_proved=False,
    finding='left/top change the DDR destination offset; gap_rows changes destination line gap; formatter writes remain identical',
    rows=rows,accepted_overflow_cases=overflow_rows,packed_alignment_cases=alignment_rows),indent=2))
