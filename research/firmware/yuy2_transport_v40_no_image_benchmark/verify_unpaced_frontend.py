"""Execute actual ARM producer and descriptors; external hardware calls mocked."""
from pathlib import Path
import json,struct
from verify_frontend import Case,m
from unicorn.arm_const import *
from elftools.elf.elffile import ELFFile
class Bench(Case):
 def __init__(self):
  self.now=1000000;self.present=True;self.pending=False;self.busy=False;self.yields=0;self.submitted=0;self.events=[]
  super().__init__()
  self.u.mem_map(0x41000000,0x10000)
  for k,v in [('ready',1),('pixels',0x41000000),('manager',0x1234),('physical',0x15b00000),('capacity',0x320000),('handle',9)]:self.set(k,v)
  for k,name in [('wait_video','bench_wait'),('submit_video','bench_submit'),('judge','bench_judge'),('send_event','bench_event')]:self.set(k,self.imp(name))
 def ret(self,r):self.u.reg_write(UC_ARM_REG_R0,r&0xffffffff);self.u.reg_write(UC_ARM_REG_PC,self.u.reg_read(UC_ARM_REG_LR))
 def hook(self,u,a,n,d):
  v=[u.reg_read(r) for r in m.R]
  if a==self.s.get('staging_size',0):
   m.put(u,v[0],1843200 if self.present else 0);m.put(u,v[1],0x11000000 if self.present else 0);self.ret(0);return
  if a==self.s['vga_resize_copy']:
   m.put(u,v[2],self.submitted+1);self.ret(1 if self.pending else 0);return
  if a in self.handlers:
   name=self.handlers[a]
   if name=='malloc':self.ret(0x41006000);return
   if name=='free':self.ret(0);return
   if name=='strchr':self.ret(0);return
   if name=='open' and m.cstr(u,v[0])=='/proc/udm/dmm_units':self.ret(11);return
   if name=='read' and v[0]==11:u.mem_write(v[1],b'row');self.ret(3);return
   if name=='sscanf':
    sp=u.reg_read(UC_ARM_REG_SP);ptrs=v[2:]+[m.word(u,sp+4*i) for i in range(8)]
    for ptr,value in zip(ptrs,[10,0x50e if self.present else 0,0,0,0,0,0,0,0x11000000,1843200]):m.put(u,ptr,value)
    self.ret(10);return
   if name=='syscall':
    assert v[0]==263 and v[1]==1;u.mem_write(v[2],struct.pack('<II',self.now//1000000,(self.now%1000000)*1000));self.now+=100;self.ret(0);return
   if name=='sched_yield':self.yields+=1;self.ret(0);return
   if name=='__errno_location':self.ret(0x41003000);return
   if name=='bench_wait':m.put(u,0x41003000,16 if self.busy else 0);self.ret(1 if self.busy else 0);return
   if name=='bench_submit':self.submitted+=1;self.ret(0);return
   if name=='bench_event':self.events.append(v[0]);self.ret(0);return
   if name=='bench_judge':self.ret(0);return
   if name=='memcpy':u.mem_write(v[0],bytes(u.mem_read(v[1],v[2])));self.ret(v[0]);return
  super().hook(u,a,n,d)
 def produce(self):
  self.u.reg_write(UC_ARM_REG_R1,0x41001000);return self.run('produce')
passed=[]
c=Bench();rr=c.produce();assert rr==0 and c.submitted==1;passed.append('unpaced_actual_ARM_producer_submits_without_sleep')
c=Bench();c.pending=True
for i in range(1000):assert c.produce()==4
assert c.submitted==0 and c.yields==1000 and not c.events;passed.append('pending_source_yields_without_fixed_delay_or_submission')
c=Bench();c.present=False
for i in range(1000):assert c.produce()==4
assert not c.events and c.yields==1000
c.now+=3000000;assert c.produce()==4 and c.events==[10];passed.append('staging_uses_elapsed_3seconds_not_30_fast_polls')
c=Bench();c.busy=True;c.set('in_flight',1)
for i in range(100):assert c.produce()==4
assert not c.submitted and c.get('in_flight')==1 and c.yields==100;passed.append('host_EBUSY_preserves_inflight_source')
c=Bench();u=c.u;out=0x41004000;old=0x41005000
u.mem_write(old,bytes(range(14)));u.reg_write(UC_ARM_REG_R1,old);c.run('make_descriptor',out)
b=bytes(u.mem_read(out,77));f=b[41:71]
assert b[:4]==bytes(range(4)) and struct.unpack_from('<H',b,4)[0]==77
assert b[19:23]==b'YUY2' and b[35]==16
assert struct.unpack_from('<HH',f,5)==(640,480)
assert struct.unpack_from('<III',f,9)==(294912000,294912000,614400)
assert f[25]==1 and struct.unpack_from('<I',f,21)[0]==166666 and struct.unpack_from('<I',f,26)[0]==166666
passed.append('actual_ARM_descriptor_640x480_8bit_YUY2_60fps_ceiling')
with Path('.local/outputs/vga-v40/build/yuy2_640_v40vga.so').open('rb') as f:
 e=ELFFile(f);imports={x.name for x in e.get_section_by_name('.dynsym').iter_symbols() if x['st_shndx']=='SHN_UNDEF'}
 assert 'usleep' not in imports and 'nanosleep' not in imports and 'sleep' not in imports
passed.append('module_has_no_timed_sleep_import')
out={'passed':passed,'camera_access':False,'hardware_calls_mocked':True};Path('.local/outputs/vga-v40/unpaced-frontend-verification.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))


