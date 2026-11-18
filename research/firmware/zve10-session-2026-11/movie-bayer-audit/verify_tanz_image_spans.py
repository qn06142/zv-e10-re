"""Execute original Tanz input-image conversion for memory and IIB routes.

Addresses, sizes and geometry are fixtures. No producer, DMA or pixels are
modeled, and formatter enums are not assigned ADC precision.
"""
import argparse
import json
import struct
import sys
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('repo',type=Path)
a=p.parse_args()
sys.path.insert(0,str(a.repo/'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness,MEM

h=Harness()
request=MEM
output=MEM+0x1000
rows=[]
spans=[2,0x20000000,0x100000,0x21000000,0x180000,0,0,0,0,0,0,0]
geometry=[2008,1134,0,0,2004,1134,4,6,1996,1122]
for kind in range(4):
    for selector in range(1,13):
        h.u.mem_write(request,bytes(0x150))
        h.u.mem_write(request+8,struct.pack('<12I',*spans))
        h.put(request+0x38,kind)
        h.put(request+0x3c,selector)
        h.u.mem_write(request+0x40,struct.pack('<10I',*geometry))
        h.put(request+0x68,0x1357)
        h.put(request+0x6c,0x2468)
        h.put(request+0x70,0x369a)
        h.u.mem_write(output,bytes([0xa5])*0xa0)
        h.run(0x636e9234,output)
        assert h.run(0x636e92b4,0,request,output)==0
        assert list(struct.unpack('<10I',h.u.mem_read(output+4,40)))==geometry
        descriptor=list(struct.unpack('<12I',h.u.mem_read(output+0x2c,48)))
        expected_kind=[0,0,1,2][kind]
        assert descriptor[0]==expected_kind
        if kind<3:
            assert descriptor[1:]==spans[:11]
        else:
            assert descriptor[1]==selector-1
            # Native IIB branch does not populate memory spans; their sentinel
            # values are intentionally not interpreted as physical addresses.
            assert descriptor[2:]==[0xa5a5a5a5]*10
        assert list(struct.unpack('<3I',h.u.mem_read(output+0x60,12)))==[0x1357,0x2468,0x369a]
        rows.append(dict(request_kind=kind,iib_selector=selector,image_descriptor=descriptor))
print(json.dumps(dict(cases=len(rows),native_image_constructor='0x636e9234',native_converter='0x636e92b4',
    native_span_converter='0x63cc33ae',mocked_boundaries=['harness memcpy/memset helpers'],
    supplied_fixtures=['spans','geometry','formatter fields','IIB selector'],
    pixel_buffers_identified=False,cadence_proved=False,rows=rows),indent=2))
