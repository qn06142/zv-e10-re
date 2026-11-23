from pathlib import Path
import runpy,contextlib,io,json,struct
from rtos_harness import *
with contextlib.redirect_stdout(io.StringIO()):c=runpy.run_path(str(Path(__file__).parent/'verify_sdf_short_parse.py'))
h=c['h'];u=h.u;obj=c['obj'];heap=MEM+0x80000;allocations=[]
def allocate(a,size):
 global heap
 p=heap;heap+=(size+15)&~15;u.mem_write(p,bytes(size));allocations.append(dict(address=hex(p),bytes=size));h.ret(p)
h.callbacks[0x63ca4b2c]=lambda a:allocate(a,a[0])
h.callbacks[0x636ba1ec]=lambda a:h.ret(MEM+0x70000)
h.callbacks[0x636ba364]=lambda a:allocate(a,a[1])
def span(a):
 u.mem_write(a[2],bytes(124));h.ret(0)
h.callbacks[0x63ca31fe]=span
stopped=[]
def stop(a):stopped.append('before exclusion/resource use and module processing');u.reg_write(UC_ARM_REG_PC,STOP)
h.callbacks[0x636c6254]=stop
h.run(0x636c5e44,obj,balanced=False);assert stopped
source=bytes(u.mem_read(obj+0xc4,60));dest=bytes(u.mem_read(obj+0x110,60));assert source[0x2f]==1 and dest[0x2f]==0
assert source[0x30]==dest[0x30]==1 and source[0x2d]==dest[0x2d]==0
out=dict(camera_access=False,original_api_builder_executed_to='0x636c6254',hardware_processing_executed=False,allocations_mocked=allocations,dmm_span_resolution_mocked=True,source_info_hex=source.hex(),destination_info_hex=dest.hex(),source_hardware_image_hex=bytes(u.mem_read(obj+0x164,124)).hex(),destination_hardware_image_hex=bytes(u.mem_read(obj+0x1e0,124)).hex(),source_compress=source[0x2f],destination_compress=dest[0x2f],source_transfer=source[0x30],destination_transfer=dest[0x30],source_iib=source[0x2d],destination_iib=dest[0x2d],limitations=['Stops before hardware module processing; does not prove driver acceptance or output packing.','Span descriptors and addresses are mocked.','The normal API forces transfer=1 and iib_number=0 for both sides; transfer=1 is not evidence of completed ISP DMA.'])
Path('.local/outputs/yc-frame-contract-20261029/sdf-native-parameter-build.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if not k.endswith('_hex')},indent=2))
